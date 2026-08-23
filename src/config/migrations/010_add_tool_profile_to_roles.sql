-- Migration 010: Add tool_profile_id to roles for role-level tool scoping
-- Version: 010
-- Date: 2026-03-18
-- Description: Extends the roles table with an optional tool profile FK so that
--              administrators can assign a default tool profile at the role level.
--              User-level profiles (from migration 006) continue to take priority
--              over role-level profiles when both are set.

-- ============================================================================
-- SCHEMA CHANGE: Add tool_profile_id column to roles
-- ============================================================================

ALTER TABLE roles
    ADD COLUMN IF NOT EXISTS tool_profile_id INTEGER
        REFERENCES tool_profiles(id) ON DELETE SET NULL;

-- Index for FK lookups and profile-based role queries
CREATE INDEX IF NOT EXISTS idx_roles_tool_profile_id ON roles(tool_profile_id);

COMMENT ON COLUMN roles.tool_profile_id IS
    'Optional tool profile for role-level tool scoping. When set, users with this role get these tools unless overridden by user-level profile.';

-- ============================================================================
-- SEED ADDITIONAL DEFAULT TOOL PROFILES
--
-- max_tools is advisory: nothing truncates a tool list to it. The only value
-- with behaviour attached is 0 which, combined with an empty operation list,
-- is the sentinel for the Full Access profile (see filter_tools_for_user).
-- The figures below are sized for the full 1,007-tool surface.
-- "Full Access" already exists from migration 006 - the INSERT below is a
-- no-op for it thanks to ON CONFLICT.
-- ============================================================================

INSERT INTO tool_profiles (name, description, max_tools, is_active, created_at, updated_at)
VALUES
    (
        'Full Access',
        'All available operations (no filtering)',
        0,
        TRUE, NOW(), NOW()
    ),
    (
        'Read-Only Analyst',
        'Every read (GET) operation across every registered ISE API',
        500,
        TRUE, NOW(), NOW()
    ),
    (
        'Network Operator',
        'Read and write access to ERS network access devices and authorization policy elements',
        120,
        TRUE, NOW(), NOW()
    ),
    (
        'Infrastructure Viewer',
        'Read-only access to deployment nodes, certificates, and directory integration',
        60,
        TRUE, NOW(), NOW()
    ),
    (
        'Troubleshooting Only',
        'Operations referenced by the built-in workflows',
        60,
        TRUE, NOW(), NOW()
    )
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- POPULATE tool_profile_operations
--
-- tool_profile_operations stores MCP tool names. Those are synthesized from
-- the spec by src/core/tool_naming.py (the ERS spec declares no operationId),
-- so they cannot be built by string concatenation in SQL - and api_endpoints
-- is still empty at migration time, because sync_api_endpoints() runs after
-- migrations complete.
--
-- The api_endpoints-derived profiles are therefore populated in code by
-- src/services/database_init.py:sync_tool_profile_operations(), which runs
-- once the endpoint registry has been synced.
--
-- "Troubleshooting Only" is the exception: its operations come from the
-- workflow steps that migration 009 has already seeded, so it can be
-- populated here.
-- ============================================================================

INSERT INTO tool_profile_operations (profile_id, operation_name, created_at)
SELECT DISTINCT
    (SELECT id FROM tool_profiles WHERE name = 'Troubleshooting Only'),
    ws.operation_name,
    NOW()
FROM workflow_steps ws
JOIN workflows w ON ws.workflow_id = w.id
WHERE w.is_active = TRUE
ON CONFLICT DO NOTHING;

-- ============================================================================
-- ASSIGN DEFAULT PROFILES TO SYSTEM ROLES
-- ============================================================================

-- Administrator gets full unrestricted access
UPDATE roles
SET tool_profile_id = (SELECT id FROM tool_profiles WHERE name = 'Full Access')
WHERE name = 'Administrator'
  AND is_system_role = TRUE;

-- Operator role maps to the Network Operator tool profile
-- (handles both "Operator" and legacy "Network Operator" names)
UPDATE roles
SET tool_profile_id = (SELECT id FROM tool_profiles WHERE name = 'Network Operator')
WHERE name IN ('Operator', 'Network Operator')
  AND is_system_role = TRUE;

-- Viewer role maps to the Read-Only Analyst tool profile
-- (handles both "Viewer" and legacy "Read-Only User" names)
UPDATE roles
SET tool_profile_id = (SELECT id FROM tool_profiles WHERE name = 'Read-Only Analyst')
WHERE name IN ('Viewer', 'Read-Only User')
  AND is_system_role = TRUE;
