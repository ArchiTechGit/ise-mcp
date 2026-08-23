"""Cisco Identity Services Engine (ISE) MCP Server implementation."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, Resource

from src.config.settings import get_settings
from src.core.api_loader import APILoader, limit_schema_depth, prune_schema
from src.core.api_registry import APIRegistry
from src.core.tool_naming import build_tool_name, describe_operation
from src.middleware.auth import AuthMiddleware
from src.middleware.logging import AuditLogger
from src.middleware.security import SecurityMiddleware

logger = logging.getLogger(__name__)

PATH_PARAM_RE = re.compile(r"\{([^}]+)\}")

# OpenAPI scalar types mapped to JSON Schema types for tool input schemas.
_SCHEMA_TYPES = {"string", "integer", "number", "boolean", "array", "object"}

#: Serialized size above which a request body schema is progressively
#: flattened, so that no single operation dominates the ``tools/list``
#: response. This is a target rather than a hard cap: flattening removes depth,
#: so a schema that is merely wide — the guest portal definitions carry
#: hundreds of settings side by side — stays above it, and keeping those field
#: names is worth more than hitting the number.
BODY_SCHEMA_SIZE_TARGET = 8192

#: Nesting depths tried, deepest first, when a body schema exceeds the target.
_BODY_SCHEMA_DEPTHS = (5, 4, 3, 2)


class ISEMCP:
    """Cisco Identity Services Engine MCP Server."""

    def __init__(self, deployment_name: Optional[str] = None):
        """Initialize the ISE MCP Server.

        Args:
            deployment_name: Optional name of the ISE deployment to bind to.
                             When None, the target is resolved per-request from
                             the authenticated user's assignment (or the first
                             active ISE deployment in the database).
        """
        self.deployment_name = deployment_name
        self.settings = get_settings()

        self.api_loader = APILoader()
        # Auth middleware is lazily created per deployment via get_auth_middleware()
        self._auth_middleware_cache: Dict[str, AuthMiddleware] = {}
        self.security_middleware = SecurityMiddleware()
        self.audit_logger = AuditLogger(deployment_name or "default")

        self.server = Server("ise-mcp")

        self.loaded_apis: Dict[str, Dict[str, Any]] = {}
        self.operations: List[Dict[str, Any]] = []
        # tool name -> operation, built once so a call never has to re-derive
        # how an operation ID was turned into a tool name.
        self.tools_by_name: Dict[str, Dict[str, Any]] = {}

        # Guidance cache
        self._tool_overrides: Dict[str, Dict[str, Any]] = {}
        self._guidance_loaded = False

    # Backwards-compatible alias: the shared multi-tenant plumbing (audit log,
    # credential store, web API) refers to the bound target as "cluster".
    @property
    def cluster_name(self) -> Optional[str]:
        """Name of the ISE deployment this instance is bound to, if any."""
        return self.deployment_name

    def get_auth_middleware(self, deployment_name: str) -> AuthMiddleware:
        """Get or create an AuthMiddleware for a specific ISE deployment."""
        if deployment_name not in self._auth_middleware_cache:
            self._auth_middleware_cache[deployment_name] = AuthMiddleware(deployment_name)
        return self._auth_middleware_cache[deployment_name]

    async def load_api(self, api_name: str) -> bool:
        """Load a specific API definition.

        Args:
            api_name: Registry key (e.g. ``"ise"``).

        Returns:
            True if loaded successfully.
        """
        api_def = APIRegistry.get_api(api_name)
        if not api_def:
            logger.error("Unknown API: %s", api_name)
            return False

        if not api_def.enabled:
            logger.info("API %s is disabled, skipping", api_name)
            return False

        spec = self.api_loader.load_openapi_spec(api_def.spec_file)
        if not spec:
            logger.error("Failed to load %s specification", api_def.display_name)
            return False

        is_valid, errors = self.api_loader.validate_spec(spec)
        if not is_valid:
            logger.error("Invalid %s spec: %s", api_def.display_name, errors)
            return False

        self.loaded_apis[api_name] = spec

        api_info = self.api_loader.get_api_info(spec)
        logger.info(
            "Loaded %s: %s v%s", api_def.display_name, api_info["title"], api_info["version"]
        )

        counts = self.api_loader.count_endpoints(spec)
        logger.info(
            "%s endpoints — Total: %d, GET: %d, POST: %d, PUT: %d, DELETE: %d, PATCH: %d",
            api_def.display_name,
            counts["total"], counts["GET"], counts["POST"],
            counts["PUT"], counts["DELETE"], counts["PATCH"],
        )

        operations = self.api_loader.list_operations(spec)
        for op in operations:
            op["api_name"] = api_name
            tool_name = build_tool_name(op["operation_id"], api_def.tool_prefix)
            op["tool_name"] = tool_name
            self.tools_by_name[tool_name] = op

        self.operations.extend(operations)
        logger.info("Found %d operations in %s", len(operations), api_def.display_name)

        return True

    async def load_guidance_cache(self) -> None:
        """Load tool description overrides from the database into cache."""
        try:
            from src.services.guidance_service import GuidanceService
            guidance_service = GuidanceService()
            overrides = await guidance_service.get_all_tool_overrides()
            self._tool_overrides = {
                op_name: override.to_dict()
                for op_name, override in overrides.items()
            }
            self._guidance_loaded = True
            logger.info("Loaded %d tool description overrides", len(self._tool_overrides))
        except Exception as exc:
            logger.warning("Failed to load guidance cache: %s", exc)
            self._tool_overrides = {}

    async def get_system_prompt(self) -> str:
        """Return the generated system prompt from the guidance service."""
        try:
            from src.services.guidance_service import GuidanceService
            guidance_service = GuidanceService()
            return await guidance_service.generate_system_prompt()
        except Exception as exc:
            logger.warning("Failed to generate system prompt: %s", exc)
            return "Cisco ISE MCP Server — identity, network access, and TrustSec APIs"

    async def get_workflows_json(self) -> str:
        """Return active workflows as a JSON string for the MCP resource."""
        try:
            from src.services.guidance_service import GuidanceService
            guidance_service = GuidanceService()
            workflows = await guidance_service.list_workflows(active_only=True)
            return json.dumps([w.to_dict() for w in workflows], indent=2)
        except Exception as exc:
            logger.warning("Failed to get workflows: %s", exc)
            return "[]"

    async def load_all_apis(self) -> int:
        """Load all enabled APIs and return the count loaded successfully."""
        loaded_count = 0
        for api_def in APIRegistry.get_enabled_apis():
            if await self.load_api(api_def.name):
                loaded_count += 1
        return loaded_count

    @staticmethod
    def _json_schema_for_param(param: Dict[str, Any]) -> Dict[str, Any]:
        """Convert an OpenAPI parameter into a JSON Schema property.

        ERS declares several parameters with a schema that carries an ``enum``
        but no ``type`` (the ``sortasc``/``sortdsc`` sort fields), so the type
        is defaulted rather than read blindly.
        """
        param_schema = param.get("schema") or {}
        param_type = param_schema.get("type")
        prop: Dict[str, Any] = {
            "type": param_type if param_type in _SCHEMA_TYPES else "string"
        }

        if prop["type"] == "array":
            items = param_schema.get("items") or {}
            item_type = items.get("type")
            prop["items"] = {"type": item_type if item_type in _SCHEMA_TYPES else "string"}
            if "enum" in items:
                prop["items"]["enum"] = items["enum"]

        if "enum" in param_schema:
            prop["enum"] = param_schema["enum"]

        description = param.get("description") or param_schema.get("description")
        prop["description"] = description or f"{param.get('in', 'query')} parameter: {param.get('name')}"

        return prop

    @staticmethod
    def _body_schema_for_operation(operation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build the JSON Schema advertised for an operation's request body.

        ERS wraps every payload in a single resource key — creating a network
        device means posting ``{"NetworkDevice": {...}}`` — so exposing the real
        schema rather than an opaque object is what makes write operations
        usable. The schema is pruned of ERS boilerplate first, then flattened
        if it is still too large to ship on every ``tools/list``.

        Args:
            operation: Normalized operation dictionary.

        Returns:
            A JSON Schema for the ``body`` property, or None if the operation
            takes no request body.
        """
        request_body = operation.get("requestBody")
        if not request_body:
            return None

        raw_schema = (
            request_body.get("content", {})
            .get("application/json", {})
            .get("schema")
        )
        if not isinstance(raw_schema, dict) or not raw_schema:
            return {"type": "object", "description": "Request body data"}

        schema = prune_schema(raw_schema)

        if len(json.dumps(schema)) > BODY_SCHEMA_SIZE_TARGET:
            for depth in _BODY_SCHEMA_DEPTHS:
                candidate = limit_schema_depth(schema, depth)
                if len(json.dumps(candidate)) <= BODY_SCHEMA_SIZE_TARGET:
                    schema = candidate
                    break
            else:
                # Still oversized: keep the shallowest form, which preserves
                # every top-level field name without the nested detail.
                schema = limit_schema_depth(schema, _BODY_SCHEMA_DEPTHS[-1])

        schema.setdefault(
            "description",
            request_body.get("description") or "Request body data",
        )
        return schema

    def _build_tool_from_operation(self, operation: Dict[str, Any]) -> Tool:
        """Build an MCP Tool from an OpenAPI operation dict."""
        method = operation["method"]
        path = operation["path"]
        api_name = operation.get("api_name", "ise")
        tool_name = operation["tool_name"]

        # ERS summaries are bare verbs ("Get-All", "Patch") that never name the
        # resource, so the headline is expanded against the operation's tag.
        headline = describe_operation(operation)
        tags = operation.get("tags") or []

        override = self._tool_overrides.get(tool_name)
        if override:
            if override.get("enhanced_description"):
                tool_description = override["enhanced_description"]
            else:
                tool_description = headline
                tool_description += f"\nEndpoint: {method} {path}"
            if override.get("usage_hint"):
                tool_description += f"\nHint: {override['usage_hint']}"
        else:
            tool_description = headline
            tool_description += f"\nEndpoint: {method} {path}"
            if tags:
                tool_description += f"\nResource: {tags[0]}"
            tool_description += f"\nAPI: {api_name}"

        path_params = PATH_PARAM_RE.findall(path)

        properties: Dict[str, Any] = {}
        required: List[str] = []

        spec_params = {
            p.get("name"): p
            for p in operation.get("parameters", [])
            if isinstance(p, dict) and p.get("name")
        }

        # Path parameters are always required.
        for param_name in path_params:
            spec_param = spec_params.get(param_name)
            if spec_param:
                properties[param_name] = self._json_schema_for_param(spec_param)
            else:
                properties[param_name] = {
                    "type": "string",
                    "description": f"Path parameter: {param_name}",
                }
            if param_name not in required:
                required.append(param_name)

        for param in operation.get("parameters", []):
            if not isinstance(param, dict):
                continue
            param_name = param.get("name")
            if not param_name or param.get("in") != "query":
                continue
            properties[param_name] = self._json_schema_for_param(param)
            if param.get("required") and param_name not in required:
                required.append(param_name)

        body_schema = self._body_schema_for_operation(operation)
        if body_schema is not None:
            properties["body"] = body_schema
            if operation["requestBody"].get("required") and "body" not in required:
                required.append("body")

        input_schema: Dict[str, Any] = {"type": "object", "properties": properties}

        if required:
            input_schema["required"] = required

        return Tool(name=tool_name, description=tool_description, inputSchema=input_schema)

    def list_all_tools(self) -> List[Tool]:
        """Build the full MCP tool list from every loaded operation."""
        return [self._build_tool_from_operation(op) for op in self.operations]

    async def handle_call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        deployment_name: Optional[str] = None,
    ) -> List[TextContent]:
        """Handle an MCP tool call.

        Args:
            name: Tool name as returned by list_tools.
            arguments: Arguments supplied by the caller.
            deployment_name: Optional ISE deployment to target.

        Returns:
            List of TextContent responses.
        """
        try:
            operation = self.tools_by_name.get(name)

            if operation is None:
                # Tolerate callers passing the raw operation ID.
                operation = next(
                    (op for op in self.operations if op["operation_id"] == name),
                    None,
                )

            if not operation:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": f"Operation {name} not found"}),
                )]

            operation_id = operation["operation_id"]
            method = operation["method"]
            path = operation["path"]
            arguments = arguments or {}

            path_params = PATH_PARAM_RE.findall(path)
            for param in path_params:
                if param in arguments and arguments[param] is not None:
                    path = path.replace(f"{{{param}}}", str(arguments[param]))
                else:
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "error": f"Missing required path parameter: {param}",
                            "required_parameters": path_params,
                        }),
                    )]

            # Route arguments to query params using the spec rather than
            # assuming every non-path argument belongs in the query string —
            # that catch-all silently sent body fields as query parameters when
            # a caller forgot to nest them under "body".
            valid_query_params = {
                param["name"]
                for param in operation.get("parameters", [])
                if isinstance(param, dict) and param.get("in") == "query" and param.get("name")
            }
            query_params = {
                k: v for k, v in arguments.items()
                if k in valid_query_params and v is not None
            }
            unrecognized = set(arguments) - set(path_params) - valid_query_params - {"body"}
            if unrecognized:
                logger.warning(
                    "Ignoring unrecognized argument(s) for %s: %s",
                    operation_id, sorted(unrecognized),
                )

            request_body = operation.get("requestBody")
            if request_body and request_body.get("required") and "body" not in arguments:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": f"Missing required request body for {operation_id}",
                        "body_schema": self._body_schema_for_operation(operation),
                    }),
                )]

            try:
                await self.security_middleware.enforce_security(
                    method=method,
                    operation_id=operation_id,
                    path=path,
                )
            except PermissionError as exc:
                error_msg = str(exc)
                await self.audit_logger.log_operation(
                    method=method,
                    path=path,
                    operation_id=operation_id,
                    error_message=error_msg,
                )
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": error_msg,
                        "type": "PermissionError",
                        "edit_mode_required": True,
                    }),
                )]

            api_name = operation.get("api_name", "ise")
            target_deployment = deployment_name or self.deployment_name or "default"
            auth_mw = self.get_auth_middleware(target_deployment)

            try:
                response = await auth_mw.execute_request(
                    method=method,
                    path=path,
                    api_name=api_name,
                    params=query_params if query_params else None,
                    json_data=arguments.get("body"),
                )

                await self.audit_logger.log_operation(
                    method=method,
                    path=path,
                    operation_id=operation_id,
                    request_body=arguments.get("body"),
                    response_status=200,
                    response_body=response,
                )

                return [TextContent(type="text", text=json.dumps(response, indent=2))]

            except Exception as exc:
                error_msg = str(exc)
                logger.error("API request failed for %s: %s", name, exc)

                await self.audit_logger.log_operation(
                    method=method,
                    path=path,
                    operation_id=operation_id,
                    error_message=error_msg,
                )

                return [TextContent(
                    type="text",
                    text=json.dumps({"error": error_msg, "type": type(exc).__name__}),
                )]

        except Exception as exc:
            logger.error("Tool execution failed for %s: %s", name, exc, exc_info=True)
            return [TextContent(
                type="text",
                text=json.dumps({"error": str(exc), "type": type(exc).__name__}),
            )]

    async def run(self) -> None:
        """Start the MCP server over stdio."""
        try:
            loaded_count = await self.load_all_apis()
            if loaded_count == 0:
                logger.error("Failed to load any APIs, exiting")
                return

            logger.info(
                "Successfully loaded %d API(s) with %d total operations",
                loaded_count, len(self.operations),
            )

            await self.load_guidance_cache()

            @self.server.call_tool()
            async def handle_tool_call(name: str, arguments: dict) -> List[TextContent]:
                return await self.handle_call_tool(name, arguments)

            @self.server.list_tools()
            async def list_tools() -> List[Tool]:
                tools = self.list_all_tools()
                logger.info("Listing %d tools", len(tools))
                return tools

            logger.info(
                "Registered tool handlers for %d operations across %d API(s)",
                len(self.operations), loaded_count,
            )

            @self.server.list_resources()
            async def list_resources() -> List[Resource]:
                return [
                    Resource(
                        uri="ise://guidance/system-prompt",
                        name="ISE API Guidance System Prompt",
                        description=(
                            "Guidance for using the ISE ERS API including resource "
                            "selection, ID-versus-name lookups, pagination and "
                            "filtering, and best practices"
                        ),
                        mimeType="text/plain",
                    ),
                    Resource(
                        uri="ise://guidance/workflows",
                        name="Common ISE Workflows",
                        description="Pre-defined workflows for common ISE administration tasks",
                        mimeType="application/json",
                    ),
                ]

            @self.server.read_resource()
            async def read_resource(uri: str) -> str:
                if uri == "ise://guidance/system-prompt":
                    return await self.get_system_prompt()
                elif uri == "ise://guidance/workflows":
                    return await self.get_workflows_json()
                raise ValueError(f"Unknown resource URI: {uri}")

            logger.info("Registered MCP resources for ISE API guidance")

            edit_mode = await self.security_middleware.is_edit_mode_enabled()
            logger.info("Edit mode: %s", "ENABLED" if edit_mode else "DISABLED (read-only)")

            async with stdio_server() as (read_stream, write_stream):
                logger.info("Cisco ISE MCP Server started via stdio")
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options(),
                )

        except Exception as exc:
            logger.error("Server error: %s", exc, exc_info=True)
            raise

    async def cleanup(self) -> None:
        """Release all resources."""
        for target, auth_mw in self._auth_middleware_cache.items():
            try:
                await auth_mw.close()
            except Exception as exc:
                logger.warning("Error closing auth middleware for '%s': %s", target, exc)
        self._auth_middleware_cache.clear()
        logger.info("Cleanup completed")
