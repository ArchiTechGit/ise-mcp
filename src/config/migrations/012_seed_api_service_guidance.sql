-- Migration 012: Guidance for the ISE API Service (Open API enablement)
-- Version: 012
-- Date: 2026-08-22
-- Description: Registers the second API in the guidance tables. GuidanceService
--              rejects category guidance for an api_name that has no
--              api_guidance row, so the parent row must exist before the
--              category row.
--
-- This API is the switch that exposes the /api/v1 Open API surface. It is NOT
-- that surface: it provides no policy, certificate, or deployment operations.

INSERT INTO api_guidance (api_name, display_name, description, when_to_use, when_not_to_use, priority, is_active, created_at, updated_at)
VALUES
    (
        'apiservice',
        'Cisco ISE API Service (Open API enablement)',
        'Reads and sets whether the ISE Open API is enabled, separately for the Policy Administration node (papIsEnabled) and the Policy Service nodes (psnsIsEnabled).',
        'Use to check whether the Open API is currently enabled, or to enable it as a prerequisite before an operator uses the /api/v1 Open API surface. These two operations require Super Admin rights - an account in the ERS Admin group reaches every ERS operation but is rejected here with a 401.',
        'Do not reach for this expecting policy, certificate, or deployment operations - it only toggles the Open API. Those operations live in the /api/v1 Open API, which is not yet loaded into this server. Everything else available today is in the ERS API.',
        20, TRUE, NOW(), NOW()
    )
ON CONFLICT (api_name) DO NOTHING;

INSERT INTO category_guidance (api_name, category_name, display_name, description, when_to_use, related_categories, priority, is_active, created_at, updated_at)
VALUES
    (
        'apiservice', 'apiService', 'Open API Enablement',
        'Two operations: read the current Open API status, and set it for the PAN and the PSNs.',
        'Read the status first. Only change it when the user has explicitly asked to enable or disable the Open API - it widens the deployment''s API attack surface, and on ISE releases before 3.4 it is disabled by default deliberately.',
        '["deployment"]', 10, TRUE, NOW(), NOW()
    )
ON CONFLICT (api_name, category_name) DO NOTHING;

-- Flag the write operation as consequential so the model treats it carefully.
INSERT INTO tool_description_overrides (operation_name, usage_hint, is_active, created_at, updated_at)
VALUES
    (
        'ise_apisvc_updateOpenAPIStatus',
        'Changes the deployment API attack surface. Read the current status with ise_apisvc_retrieveOpenAPIStatus first, confirm the intent with the user, and send both papIsEnabled and psnsIsEnabled explicitly - an omitted field is not preserved.',
        TRUE, NOW(), NOW()
    )
ON CONFLICT (operation_name) DO UPDATE SET
    usage_hint = EXCLUDED.usage_hint,
    updated_at = NOW();
