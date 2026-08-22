-- Migration 011: Record the derived MCP tool name for each API endpoint
--
-- Root cause: role_operations and tool_profile_operations store the MCP tool
-- name, which previously equalled "{api_name}_{operation_id}". The ISE ERS
-- specification declares no operationId at all — 395 operations identify
-- themselves only by a tag and a repeated summary such as "Get-All" — so both
-- the operation ID and the tool name are synthesized by
-- src/core/tool_naming.py and can no longer be reconstructed in SQL.
--
-- Storing the derived name alongside the operation keeps RBAC filtering,
-- tool profiles, and the operations picker in the web UI all matching the
-- names the MCP server actually advertises.

ALTER TABLE api_endpoints ADD COLUMN IF NOT EXISTS tool_name VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_api_endpoints_tool_name ON api_endpoints(tool_name);

-- Endpoints synced before this migration carry no tool name; sync_api_endpoints()
-- repopulates them on the next startup.
