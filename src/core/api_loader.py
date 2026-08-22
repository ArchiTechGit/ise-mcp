"""API loader for the Cisco ISE ERS OpenAPI specification."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from src.core.tool_naming import build_operation_ids

logger = logging.getLogger(__name__)

ISE_ERS_SPEC_FILE = "ERS_APIs.yaml"

HTTP_METHODS = ("get", "post", "put", "delete", "patch", "head", "options")

#: Schema keywords the ERS spec sets to placeholder values on almost every
#: property (``"example": null``, ``"title"`` echoing the property name). They
#: add tens of thousands of tokens to the tool list without telling a model
#: anything, so they are stripped when a schema is exposed as a tool input.
_NOISE_KEYS = frozenset({"title", "example", "examples", "xml", "externalDocs", "deprecated"})

#: ERS documents string enumerations in prose — ``"allowed values:ASCII,HEXADECIMAL"``
#: — and frequently types those very fields as ``object``. Left alone, a client
#: following the schema would send ``{}`` where ISE expects ``"ASCII"``.
_ALLOWED_VALUES_RE = re.compile(r"allowed\s+values\s*:\s*(?P<values>[^.]+)", re.IGNORECASE)
_ENUM_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.\- ]+$")

try:  # libyaml parses the 60k-line ERS spec roughly 10x faster
    _YamlLoader = yaml.CSafeLoader
except AttributeError:  # pragma: no cover - depends on the local libyaml build
    _YamlLoader = yaml.SafeLoader


def prune_schema(node: Any) -> Any:
    """Strip ERS boilerplate from a JSON schema and repair prose enumerations.

    Two transforms are applied to every schema node:

    * placeholder keywords (:data:`_NOISE_KEYS`) and empty descriptions are
      dropped, which halves the serialized size of the ERS request bodies;
    * a leaf whose description spells out ``allowed values: A, B, C`` gains a
      real ``enum``, and is retyped from ``object`` to ``string`` when ISE
      mistyped it.

    The walk is schema-aware rather than a blind key filter, because the keys
    inside a ``properties`` map are field names chosen by Cisco, not schema
    keywords: 228 ERS resources define a field called ``description`` and one
    defines a field called ``title``. Filtering those by name would silently
    delete real fields from the request body.

    Args:
        node: Any fragment of a resolved JSON schema.

    Returns:
        A new fragment; the input is never mutated.
    """
    if isinstance(node, list):
        return [prune_schema(item) for item in node]

    if not isinstance(node, dict):
        return node

    pruned: Dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            # Field names, not keywords — prune each field's schema, keep every name.
            pruned[key] = {name: prune_schema(sub) for name, sub in value.items()}
            continue
        if key in _NOISE_KEYS:
            continue
        if key == "description" and not value:
            continue
        pruned[key] = prune_schema(value)

    _apply_prose_enum(pruned)
    return pruned


def _apply_prose_enum(schema: Dict[str, Any]) -> None:
    """Give a leaf schema a real ``enum`` when its description declares one."""
    if "enum" in schema or "properties" in schema or "items" in schema:
        return

    description = schema.get("description")
    if not isinstance(description, str):
        return

    match = _ALLOWED_VALUES_RE.search(description)
    if not match:
        return

    values = [v.strip() for v in match.group("values").split(",")]
    if len(values) < 2 or not all(v and _ENUM_TOKEN_RE.fullmatch(v) for v in values):
        return

    schema["enum"] = values
    # ERS types these fields as `object`, which is simply wrong for a value
    # drawn from a fixed list of strings.
    if schema.get("type") in (None, "object"):
        schema["type"] = "string"


def limit_schema_depth(node: Any, max_depth: int, _depth: int = 0) -> Any:
    """Collapse a schema below ``max_depth`` to keep the tool list bounded.

    A handful of ERS bodies (the guest portal definitions) nest far enough to
    serialize into tens of kilobytes each. Truncating their deepest levels
    keeps the shape of the request visible without shipping the whole tree to
    every client on every ``tools/list``.

    Args:
        node: Schema fragment.
        max_depth: Levels of ``properties``/``items`` nesting to keep.
        _depth: Current recursion depth; callers should not set this.

    Returns:
        A new fragment truncated to ``max_depth``.
    """
    if isinstance(node, list):
        return [limit_schema_depth(item, max_depth, _depth) for item in node]

    if not isinstance(node, dict):
        return node

    if _depth >= max_depth and ("properties" in node or "items" in node):
        collapsed: Dict[str, Any] = {"type": node.get("type", "object")}
        description = node.get("description")
        names = list(node.get("properties") or {})
        if names:
            detail = f"Nested object with fields: {', '.join(names[:12])}"
            collapsed["description"] = f"{description} {detail}" if description else detail
        elif description:
            collapsed["description"] = description
        return collapsed

    limited: Dict[str, Any] = {}
    for key, value in node.items():
        # `properties` maps field names to schemas, so the depth step happens on
        # its values. Recursing into the map itself would treat field names as
        # keywords and never descend at all.
        if key == "properties" and isinstance(value, dict):
            limited[key] = {
                name: limit_schema_depth(sub, max_depth, _depth + 1)
                for name, sub in value.items()
            }
        elif key in ("items", "additionalProperties") and isinstance(value, dict):
            limited[key] = limit_schema_depth(value, max_depth, _depth + 1)
        else:
            limited[key] = value
    return limited


class APILoader:
    """Loader for the Cisco ISE ERS OpenAPI specification."""

    def __init__(self, specs_dir: str = "openapi_specs"):
        """Initialize the API loader.

        Args:
            specs_dir: Directory containing OpenAPI specification files.
        """
        self.specs_dir = Path(specs_dir)
        self.loaded_specs: Dict[str, Dict[str, Any]] = {}

    def load_openapi_spec(self, spec_file: str) -> Optional[Dict[str, Any]]:
        """Load and fully dereference an OpenAPI specification file.

        Both YAML (``.yaml``/``.yml``) and JSON specs are supported; the ISE
        ERS API ships as YAML.

        Args:
            spec_file: Name of the OpenAPI spec file within ``specs_dir``.

        Returns:
            The specification as a dictionary, or None if loading fails.
        """
        spec_path = self.specs_dir / spec_file

        if not spec_path.exists():
            logger.error("OpenAPI spec file not found: %s", spec_path)
            return None

        try:
            with open(spec_path, "r", encoding="utf-8") as handle:
                if spec_path.suffix.lower() in (".yaml", ".yml"):
                    spec = yaml.load(handle, Loader=_YamlLoader)
                else:
                    spec = json.load(handle)

            if not isinstance(spec, dict):
                logger.error("OpenAPI spec %s did not parse to a mapping", spec_file)
                return None

            spec = self._resolve_refs(spec)
            logger.info("Successfully loaded OpenAPI spec: %s", spec_file)
            return spec

        except (yaml.YAMLError, json.JSONDecodeError) as exc:
            logger.error("Failed to parse OpenAPI spec %s: %s", spec_file, exc)
            return None
        except Exception as exc:
            logger.error("Error loading OpenAPI spec %s: %s", spec_file, exc)
            return None

    def _resolve_refs(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively resolve local ``$ref`` pointers within a spec document.

        The ERS spec expresses its shared pagination parameters and every
        request and response schema as ``{"$ref": "#/components/..."}``
        pointers. Downstream code — tool schema generation and request routing
        alike — needs the objects themselves, so they are expanded once here at
        load time.

        Args:
            spec: Raw OpenAPI specification dictionary.

        Returns:
            A new dictionary with all local ``$ref`` pointers replaced by the
            objects they point to. External refs (not starting with ``#/``) are
            left untouched.
        """

        def resolve_pointer(ref: str) -> Any:
            parts = [p.replace("~1", "/").replace("~0", "~") for p in ref[2:].split("/")]
            node: Any = spec
            for part in parts:
                node = node[part]
            return node

        def deref(node: Any, seen: frozenset) -> Any:
            if isinstance(node, dict):
                ref = node.get("$ref")
                if isinstance(ref, str) and ref.startswith("#/"):
                    if ref in seen:
                        logger.warning("Circular $ref detected while resolving spec: %s", ref)
                        return {}
                    return deref(resolve_pointer(ref), seen | {ref})
                return {k: deref(v, seen) for k, v in node.items()}
            if isinstance(node, list):
                return [deref(item, seen) for item in node]
            return node

        return deref(spec, frozenset())

    def get_api_info(self, spec: Dict[str, Any]) -> Dict[str, str]:
        """Extract API info (title, version, description) from the spec."""
        info = spec.get("info", {})
        return {
            "title": info.get("title", "Unknown API"),
            "version": info.get("version", "Unknown"),
            "description": info.get("description", ""),
        }

    def count_endpoints(self, spec: Dict[str, Any]) -> Dict[str, int]:
        """Count endpoints by HTTP method."""
        counts: Dict[str, int] = {"GET": 0, "POST": 0, "PUT": 0, "DELETE": 0, "PATCH": 0, "total": 0}
        for path_item in spec.get("paths", {}).values():
            if not isinstance(path_item, dict):
                continue
            for method in ("get", "post", "put", "delete", "patch"):
                if method in path_item:
                    counts[method.upper()] += 1
                    counts["total"] += 1
        return counts

    def list_operations(self, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return every operation in the spec as a normalized dictionary.

        Path-level ``parameters`` are merged into each operation, and a stable
        operation ID is assigned by
        :func:`src.core.tool_naming.build_operation_ids` — taken from the spec's
        own ``operationId`` where one exists, and synthesized from the tag and
        summary where it does not (the ERS spec declares none at all).

        Args:
            spec: Dereferenced OpenAPI specification dictionary.

        Returns:
            List of operation dictionaries in specification order.
        """
        operations: List[Dict[str, Any]] = []

        for path, path_item in spec.get("paths", {}).items():
            if not isinstance(path_item, dict):
                continue

            shared_params = path_item.get("parameters", []) or []

            for method in HTTP_METHODS:
                operation = path_item.get(method)
                if not isinstance(operation, dict):
                    continue

                parameters = list(shared_params) + list(operation.get("parameters", []) or [])

                operations.append({
                    "method": method.upper(),
                    "path": path,
                    # Preserved so tool_naming can prefer a declared ID over a
                    # synthesized one. The ERS spec declares none; the API
                    # Service spec declares one per operation.
                    "operationId": operation.get("operationId"),
                    "summary": operation.get("summary", ""),
                    "description": operation.get("description", ""),
                    "tags": operation.get("tags", []),
                    "parameters": parameters,
                    "requestBody": operation.get("requestBody"),
                })

        for operation, operation_id in zip(operations, build_operation_ids(operations)):
            operation["operation_id"] = operation_id

        return operations

    def get_base_url(self, spec: Dict[str, Any]) -> Optional[str]:
        """Extract the first server URL from the spec."""
        servers = spec.get("servers", [])
        if servers:
            return servers[0].get("url")
        return None

    def validate_spec(self, spec: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate basic OpenAPI spec structure."""
        errors: List[str] = []

        if "openapi" not in spec and "swagger" not in spec:
            errors.append("Missing 'openapi' or 'swagger' version field")

        if "info" not in spec:
            errors.append("Missing 'info' section")

        if "paths" not in spec:
            errors.append("Missing 'paths' section")
        elif not spec["paths"]:
            errors.append("No paths defined in specification")

        return len(errors) == 0, errors

    def load_all_apis(self) -> Dict[str, Dict[str, Any]]:
        """Load every enabled ISE OpenAPI specification.

        Returns:
            Dict keyed by API name mapping to the spec dict. An API whose spec
            fails to load or validate is omitted rather than aborting the
            others.
        """
        from src.core.api_registry import APIRegistry

        loaded: Dict[str, Dict[str, Any]] = {}

        for api_def in APIRegistry.get_enabled_apis():
            spec = self.load_openapi_spec(api_def.spec_file)
            if not spec:
                logger.error(
                    "Failed to load %s OpenAPI spec (%s)",
                    api_def.display_name, api_def.spec_file,
                )
                continue

            is_valid, errors = self.validate_spec(spec)
            if not is_valid:
                logger.error("Invalid %s OpenAPI spec: %s", api_def.display_name, errors)
                continue

            loaded[api_def.name] = spec
            logger.info("Validated and loaded %s spec", api_def.display_name)

        self.loaded_specs = loaded
        return loaded
