-- Migration 005: Align role operation names with MCP tool names
--
-- Historically this migration prefixed role_operations entries with the API
-- name, because tool names were "{api_name}_{operation_id}".
--
-- That no longer holds for the ISE ERS API: the specification declares no
-- operationId, so operation IDs are synthesized from each operation's tag and
-- summary (see src/core/tool_naming.py). Blindly prefixing would produce names
-- that never match a real tool, silently disabling role-based filtering.
--
-- Migration 011 adds api_endpoints.tool_name and sync_api_endpoints()
-- populates it, so the mapping is resolved there instead. This migration now
-- only removes duplicate role_operations rows left over from earlier schemas.

DELETE FROM role_operations
WHERE id NOT IN (
    SELECT MIN(id)
    FROM role_operations
    GROUP BY role_id, operation_name
);
