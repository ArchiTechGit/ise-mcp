-- Migration 009: Seed built-in Cisco ISE workflows and use cases
-- Version: 009
-- Date: 2026-08-19
-- Description: Seeds 8 practical ISE workflows with steps and 6 use cases
--              covering device onboarding, identity and endpoint management,
--              guest access, TrustSec, threat containment, and deployment health.
--
-- Every operation_name below is a real MCP tool name produced by
-- src/core/tool_naming.py from the ERS_APIs.yaml specification.

-- ============================================================================
-- WORKFLOWS
-- ============================================================================

INSERT INTO workflows (name, display_name, description, problem_statement, use_case_tags, is_active, priority, created_at, updated_at)
VALUES
    (
        'network_device_onboarding',
        'Network Access Device Onboarding',
        'Review the existing device group hierarchy and profiles, check the device is not already present, create the network device with its RADIUS or TACACS+ settings, then read it back to confirm.',
        'Onboard a switch, wireless controller, or firewall as a RADIUS/TACACS+ client of ISE.',
        '["onboarding", "network-device", "radius", "tacacs"]',
        TRUE, 100, NOW(), NOW()
    ),
    (
        'endpoint_investigation',
        'Endpoint Investigation',
        'Look up an endpoint by MAC address, review its identity group and profiling result, and check whether it is currently rejected or under an ANC action.',
        'Find out what ISE knows about a specific endpoint and why it is being treated the way it is.',
        '["endpoint", "troubleshooting", "profiling"]',
        TRUE, 95, NOW(), NOW()
    ),
    (
        'anc_threat_containment',
        'ANC Threat Containment',
        'Confirm the ANC policy to apply, quarantine the offending endpoint by MAC address, verify the action took effect, and clear it once remediation is complete.',
        'Contain a compromised or misbehaving endpoint and release it afterwards.',
        '["security", "anc", "quarantine", "incident-response"]',
        TRUE, 90, NOW(), NOW()
    ),
    (
        'guest_account_lifecycle',
        'Guest Account Lifecycle',
        'Review guest types and sponsor groups, create a guest account, notify the guest, and suspend or reinstate it as required.',
        'Create and manage a guest account through its full lifecycle.',
        '["guest", "sponsor", "onboarding"]',
        TRUE, 85, NOW(), NOW()
    ),
    (
        'authorization_policy_audit',
        'Authorization Policy Element Audit',
        'Enumerate the policy building blocks — authorization profiles, downloadable ACLs, and allowed protocol services — and inspect the definitions behind them.',
        'Understand what ISE returns on a successful authorization and which EAP methods are permitted.',
        '["policy", "audit", "authorization"]',
        TRUE, 80, NOW(), NOW()
    ),
    (
        'trustsec_policy_review',
        'TrustSec Segmentation Review',
        'Walk the TrustSec configuration: security group tags, SGACLs, and the egress matrix cells that bind them into a segmentation policy.',
        'Review or document the current TrustSec segmentation policy.',
        '["trustsec", "segmentation", "sgt", "audit"]',
        TRUE, 75, NOW(), NOW()
    ),
    (
        'identity_source_review',
        'Identity Source Review',
        'Review internal users and identity groups, then inspect the external identity sources — Active Directory join points and LDAP stores — and the sequences that order them.',
        'Determine which identity stores ISE will consult for an authentication and in what order.',
        '["identity", "active-directory", "ldap", "audit"]',
        TRUE, 70, NOW(), NOW()
    ),
    (
        'deployment_health_check',
        'ISE Deployment Health Check',
        'Review the deployment topology, each node and its personas, session service nodes, and pxGrid registration to confirm the deployment is intact.',
        'Verify the ISE deployment is healthy and every node is playing its expected role.',
        '["health", "deployment", "monitoring", "nodes"]',
        TRUE, 65, NOW(), NOW()
    )
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- WORKFLOW STEPS
-- ============================================================================

-- 1. Network Access Device Onboarding
INSERT INTO workflow_steps (workflow_id, step_order, operation_name, description, expected_output, optional, created_at)
SELECT w.id, v.step_order, v.operation_name, v.description, v.expected_output, v.optional, NOW()
FROM workflows w
CROSS JOIN (VALUES
    (1, 'ise_networkdevicegroup_getAll', 'List the network device group hierarchy so the new device lands in the right Location and Device Type groups', 'Device groups with their names, ids, and root hierarchy', FALSE),
    (2, 'ise_networkdevice_getByName', 'Confirm the device is not already onboarded under this name', 'The existing device, or a 404 confirming the name is free', FALSE),
    (3, 'ise_networkdevice_create', 'Create the network device with its IP list, device groups, and RADIUS or TACACS+ shared secret', '201 Created with the new device UUID in the Location header', FALSE),
    (4, 'ise_networkdevice_getByName', 'Read the device back to confirm the settings ISE actually stored', 'Full NetworkDevice object including authentication settings and group membership', FALSE),
    (5, 'ise_networkdevice_getAll', 'Optionally confirm the device appears in the overall inventory', 'SearchResult containing the newly created device', TRUE)
) AS v(step_order, operation_name, description, expected_output, optional)
WHERE w.name = 'network_device_onboarding'
AND NOT EXISTS (
    SELECT 1 FROM workflow_steps ws WHERE ws.workflow_id = w.id AND ws.step_order = v.step_order
);

-- 2. Endpoint Investigation
INSERT INTO workflow_steps (workflow_id, step_order, operation_name, description, expected_output, optional, created_at)
SELECT w.id, v.step_order, v.operation_name, v.description, v.expected_output, v.optional, NOW()
FROM workflows w
CROSS JOIN (VALUES
    (1, 'ise_endpoint_getByName', 'Look up the endpoint by its MAC address (endpoints are keyed by MAC, not by UUID)', 'Endpoint object with its group assignment and profiling attributes', FALSE),
    (2, 'ise_endpointgroup_getById', 'Resolve the endpoint identity group the endpoint belongs to', 'Endpoint group name and description', FALSE),
    (3, 'ise_profilerprofile_getAll', 'Review the profiler policies that could match this endpoint', 'Profiler profile list with names and ids', TRUE),
    (4, 'ise_endpoint_getRejectedEndpoints', 'Check whether the endpoint has been rejected during registration', 'List of rejected endpoints', TRUE),
    (5, 'ise_ancendpoint_getAll', 'Check whether an ANC action is currently applied to the endpoint', 'ANC endpoint assignments with MAC address and policy name', TRUE)
) AS v(step_order, operation_name, description, expected_output, optional)
WHERE w.name = 'endpoint_investigation'
AND NOT EXISTS (
    SELECT 1 FROM workflow_steps ws WHERE ws.workflow_id = w.id AND ws.step_order = v.step_order
);

-- 3. ANC Threat Containment
INSERT INTO workflow_steps (workflow_id, step_order, operation_name, description, expected_output, optional, created_at)
SELECT w.id, v.step_order, v.operation_name, v.description, v.expected_output, v.optional, NOW()
FROM workflows w
CROSS JOIN (VALUES
    (1, 'ise_ancpolicy_getAll', 'List the ANC policies available and pick the action to apply (QUARANTINE, PORTBOUNCE, SHUTDOWN, REAUTHENTICATE)', 'ANC policies with their names and actions', FALSE),
    (2, 'ise_endpoint_getByName', 'Confirm the endpoint exists and note its current group before containing it', 'Endpoint object for the MAC address in question', FALSE),
    (3, 'ise_ancendpoint_apply', 'Apply the ANC policy to the endpoint MAC address to contain it', 'Success response confirming the policy was applied', FALSE),
    (4, 'ise_ancendpoint_getAll', 'Verify the ANC assignment is now in place', 'ANC endpoint entry showing the MAC address and policy name', FALSE),
    (5, 'ise_ancendpoint_clear', 'Clear the ANC action once the endpoint has been remediated', 'Success response confirming the policy was removed', TRUE)
) AS v(step_order, operation_name, description, expected_output, optional)
WHERE w.name = 'anc_threat_containment'
AND NOT EXISTS (
    SELECT 1 FROM workflow_steps ws WHERE ws.workflow_id = w.id AND ws.step_order = v.step_order
);

-- 4. Guest Account Lifecycle
INSERT INTO workflow_steps (workflow_id, step_order, operation_name, description, expected_output, optional, created_at)
SELECT w.id, v.step_order, v.operation_name, v.description, v.expected_output, v.optional, NOW()
FROM workflows w
CROSS JOIN (VALUES
    (1, 'ise_guesttype_getAll', 'List guest types to choose the access duration and portal behaviour for the account', 'Guest types with their names and ids', FALSE),
    (2, 'ise_sponsorgroup_getAll', 'Confirm which sponsor group is permitted to create this kind of account', 'Sponsor groups with their permissions', TRUE),
    (3, 'ise_guestuser_create', 'Create the guest account with its guest type, person details, and access window', '201 Created with the new guest user UUID in the Location header', FALSE),
    (4, 'ise_guestuser_email', 'Send the account credentials to the guest by email (use ise_guestuser_sms for SMS)', 'Success response confirming the notification was sent', TRUE),
    (5, 'ise_guestuser_suspendByName', 'Suspend the account if access must be revoked early', 'Success response confirming suspension', TRUE),
    (6, 'ise_guestuser_reinstateByName', 'Reinstate a suspended account once access should resume', 'Success response confirming reinstatement', TRUE)
) AS v(step_order, operation_name, description, expected_output, optional)
WHERE w.name = 'guest_account_lifecycle'
AND NOT EXISTS (
    SELECT 1 FROM workflow_steps ws WHERE ws.workflow_id = w.id AND ws.step_order = v.step_order
);

-- 5. Authorization Policy Element Audit
INSERT INTO workflow_steps (workflow_id, step_order, operation_name, description, expected_output, optional, created_at)
SELECT w.id, v.step_order, v.operation_name, v.description, v.expected_output, v.optional, NOW()
FROM workflows w
CROSS JOIN (VALUES
    (1, 'ise_authorizationprofile_getAll', 'List every authorization profile defined in the deployment', 'Authorization profiles with names and ids', FALSE),
    (2, 'ise_authorizationprofile_getById', 'Inspect a profile to see the VLAN, dACL, SGT, and reauthentication settings it returns', 'Full authorization profile definition', FALSE),
    (3, 'ise_downloadableacl_getAll', 'List the downloadable ACLs that authorization profiles can reference', 'dACL names and ids', FALSE),
    (4, 'ise_downloadableacl_getById', 'Read the ACE content of a specific downloadable ACL', 'dACL definition with its ACE lines', FALSE),
    (5, 'ise_allowedprotocols_getAll', 'List the allowed protocol services that control which EAP methods are permitted', 'Allowed protocol service names and ids', TRUE),
    (6, 'ise_allowedprotocols_getById', 'Inspect an allowed protocol service to see the enabled EAP methods and settings', 'Allowed protocols definition', TRUE)
) AS v(step_order, operation_name, description, expected_output, optional)
WHERE w.name = 'authorization_policy_audit'
AND NOT EXISTS (
    SELECT 1 FROM workflow_steps ws WHERE ws.workflow_id = w.id AND ws.step_order = v.step_order
);

-- 6. TrustSec Segmentation Review
INSERT INTO workflow_steps (workflow_id, step_order, operation_name, description, expected_output, optional, created_at)
SELECT w.id, v.step_order, v.operation_name, v.description, v.expected_output, v.optional, NOW()
FROM workflows w
CROSS JOIN (VALUES
    (1, 'ise_sgt_getAll', 'List the security group tags defined in the deployment', 'SGTs with their names, values, and ids', FALSE),
    (2, 'ise_sgacl_getAll', 'List the SGACLs available to the egress matrix', 'SGACL names and ids', FALSE),
    (3, 'ise_sgacl_getById', 'Read the ACE content of a specific SGACL', 'SGACL definition with its permit/deny rules', TRUE),
    (4, 'ise_egressmatrixcell_getAll', 'Enumerate the egress matrix cells that bind source SGT, destination SGT, and SGACL', 'Matrix cells with their source, destination, and policy', FALSE),
    (5, 'ise_egressmatrixcell_getById', 'Inspect a specific matrix cell to see its default rule and assigned SGACLs', 'Full egress matrix cell definition', TRUE),
    (6, 'ise_sxplocalbindings_getAll', 'Review static IP-to-SGT bindings propagated over SXP', 'SXP local bindings with IP, SGT, and VPN', TRUE)
) AS v(step_order, operation_name, description, expected_output, optional)
WHERE w.name = 'trustsec_policy_review'
AND NOT EXISTS (
    SELECT 1 FROM workflow_steps ws WHERE ws.workflow_id = w.id AND ws.step_order = v.step_order
);

-- 7. Identity Source Review
INSERT INTO workflow_steps (workflow_id, step_order, operation_name, description, expected_output, optional, created_at)
SELECT w.id, v.step_order, v.operation_name, v.description, v.expected_output, v.optional, NOW()
FROM workflows w
CROSS JOIN (VALUES
    (1, 'ise_identitygroup_getAll', 'List the internal identity groups users can belong to', 'Identity groups with names and ids', FALSE),
    (2, 'ise_internaluser_getAll', 'List internal users, filtering by name or group as needed', 'SearchResult of internal users', FALSE),
    (3, 'ise_activedirectory_getAllJoinPoints', 'List the Active Directory join points configured on the deployment', 'AD join points with their domain names and ids', FALSE),
    (4, 'ise_activedirectory_getJoinPointDetails', 'Inspect a join point to see its domain, groups, and attribute configuration', 'Full AD join point definition', TRUE),
    (5, 'ise_ldap_getAll', 'List LDAP identity sources configured alongside Active Directory', 'LDAP store names and ids', TRUE),
    (6, 'ise_idstoresequence_getAll', 'Review identity store sequences to see the order in which stores are consulted', 'Identity store sequences with their ordered store lists', FALSE)
) AS v(step_order, operation_name, description, expected_output, optional)
WHERE w.name = 'identity_source_review'
AND NOT EXISTS (
    SELECT 1 FROM workflow_steps ws WHERE ws.workflow_id = w.id AND ws.step_order = v.step_order
);

-- 8. ISE Deployment Health Check
INSERT INTO workflow_steps (workflow_id, step_order, operation_name, description, expected_output, optional, created_at)
SELECT w.id, v.step_order, v.operation_name, v.description, v.expected_output, v.optional, NOW()
FROM workflows w
CROSS JOIN (VALUES
    (1, 'ise_deploymentinfo_getAllInfo', 'Read the overall deployment information for the ISE cluster', 'Deployment summary across all nodes', FALSE),
    (2, 'ise_node_getAll', 'List every node in the deployment', 'Node names and ids', FALSE),
    (3, 'ise_node_getByName', 'Inspect a node to confirm its personas and services', 'Node detail including persona and service roles', FALSE),
    (4, 'ise_sessionservicenode_getAll', 'Confirm which nodes are providing session services', 'Session service nodes with their group assignment', TRUE),
    (5, 'ise_pxgridnode_getAll', 'Review pxGrid client registration state', 'pxGrid nodes with their registration status', TRUE),
    (6, 'ise_telemetryinfo_getAll', 'Check telemetry configuration and reporting status', 'Telemetry info records', TRUE)
) AS v(step_order, operation_name, description, expected_output, optional)
WHERE w.name = 'deployment_health_check'
AND NOT EXISTS (
    SELECT 1 FROM workflow_steps ws WHERE ws.workflow_id = w.id AND ws.step_order = v.step_order
);

-- ============================================================================
-- USE CASES
-- ============================================================================

INSERT INTO use_cases (name, display_name, description, category, is_active, created_at, updated_at)
VALUES
    (
        'device_onboarding',
        'Device Onboarding',
        'Bring network access devices under ISE control with the correct device groups, shared secrets, and protocol settings.',
        'operations',
        TRUE, NOW(), NOW()
    ),
    (
        'access_troubleshooting',
        'Access Troubleshooting',
        'Work out why an endpoint or user is being denied, quarantined, or given the wrong level of access.',
        'troubleshooting',
        TRUE, NOW(), NOW()
    ),
    (
        'incident_response',
        'Incident Response',
        'Contain a compromised endpoint quickly and release it once the threat has been remediated.',
        'security',
        TRUE, NOW(), NOW()
    ),
    (
        'guest_management',
        'Guest Management',
        'Create, notify, suspend, and reinstate guest accounts, and review the sponsor and portal configuration behind them.',
        'operations',
        TRUE, NOW(), NOW()
    ),
    (
        'policy_audit',
        'Policy Audit',
        'Document what the deployment actually enforces: authorization profiles, ACLs, protocol services, and TrustSec segmentation.',
        'compliance',
        TRUE, NOW(), NOW()
    ),
    (
        'deployment_monitoring',
        'Deployment Monitoring',
        'Regular checks on node personas, services, and identity source integration to catch deployment problems early.',
        'monitoring',
        TRUE, NOW(), NOW()
    )
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- USE CASE <-> WORKFLOW LINKS
-- ============================================================================

INSERT INTO use_case_workflows (use_case_id, workflow_id, created_at)
SELECT uc.id, w.id, NOW()
FROM use_cases uc, workflows w
WHERE (uc.name, w.name) IN (
    ('device_onboarding', 'network_device_onboarding'),
    ('access_troubleshooting', 'endpoint_investigation'),
    ('access_troubleshooting', 'authorization_policy_audit'),
    ('incident_response', 'anc_threat_containment'),
    ('guest_management', 'guest_account_lifecycle'),
    ('policy_audit', 'authorization_policy_audit'),
    ('policy_audit', 'trustsec_policy_review'),
    ('deployment_monitoring', 'deployment_health_check'),
    ('deployment_monitoring', 'identity_source_review')
)
ON CONFLICT (use_case_id, workflow_id) DO NOTHING;
