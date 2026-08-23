-- Migration: Add API Guidance System
-- Version: 004
-- Date: 2025-12-04
-- Description: Adds tables for API guidance, workflows, tool descriptions, and system prompts

-- API-level guidance table
CREATE TABLE IF NOT EXISTS api_guidance (
    id SERIAL PRIMARY KEY,
    api_name VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    when_to_use TEXT,
    when_not_to_use TEXT,
    examples JSONB DEFAULT '[]',
    priority INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Category/tag guidance table
CREATE TABLE IF NOT EXISTS category_guidance (
    id SERIAL PRIMARY KEY,
    api_name VARCHAR(50) NOT NULL,
    category_name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    description TEXT,
    when_to_use TEXT,
    related_categories JSONB DEFAULT '[]',
    priority INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(api_name, category_name)
);

-- Workflow definitions table
CREATE TABLE IF NOT EXISTS workflows (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    description TEXT,
    problem_statement TEXT,
    use_case_tags JSONB DEFAULT '[]',
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Workflow steps table
CREATE TABLE IF NOT EXISTS workflow_steps (
    id SERIAL PRIMARY KEY,
    workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    operation_name VARCHAR(255) NOT NULL,
    description TEXT,
    expected_output TEXT,
    optional BOOLEAN DEFAULT FALSE,
    fallback_operation VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(workflow_id, step_order)
);

-- Tool description overrides table
CREATE TABLE IF NOT EXISTS tool_description_overrides (
    id SERIAL PRIMARY KEY,
    operation_name VARCHAR(255) NOT NULL UNIQUE,
    enhanced_description TEXT,
    usage_hint TEXT,
    related_tools JSONB DEFAULT '[]',
    common_parameters JSONB DEFAULT '[]',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- System prompt sections table
CREATE TABLE IF NOT EXISTS system_prompt_sections (
    id SERIAL PRIMARY KEY,
    section_name VARCHAR(100) NOT NULL UNIQUE,
    section_order INTEGER DEFAULT 0,
    title VARCHAR(255),
    content TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_api_guidance_api_name ON api_guidance(api_name);
CREATE INDEX IF NOT EXISTS idx_api_guidance_priority ON api_guidance(priority);
CREATE INDEX IF NOT EXISTS idx_api_guidance_is_active ON api_guidance(is_active);

CREATE INDEX IF NOT EXISTS idx_category_guidance_api_name ON category_guidance(api_name);
CREATE INDEX IF NOT EXISTS idx_category_guidance_category_name ON category_guidance(category_name);
CREATE INDEX IF NOT EXISTS idx_category_guidance_priority ON category_guidance(priority);
CREATE INDEX IF NOT EXISTS idx_category_guidance_is_active ON category_guidance(is_active);

CREATE INDEX IF NOT EXISTS idx_workflows_name ON workflows(name);
CREATE INDEX IF NOT EXISTS idx_workflows_priority ON workflows(priority);
CREATE INDEX IF NOT EXISTS idx_workflows_is_active ON workflows(is_active);

CREATE INDEX IF NOT EXISTS idx_workflow_steps_workflow_id ON workflow_steps(workflow_id);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_step_order ON workflow_steps(workflow_id, step_order);

CREATE INDEX IF NOT EXISTS idx_tool_description_overrides_operation_name ON tool_description_overrides(operation_name);
CREATE INDEX IF NOT EXISTS idx_tool_description_overrides_is_active ON tool_description_overrides(is_active);

CREATE INDEX IF NOT EXISTS idx_system_prompt_sections_section_name ON system_prompt_sections(section_name);
CREATE INDEX IF NOT EXISTS idx_system_prompt_sections_section_order ON system_prompt_sections(section_order);
CREATE INDEX IF NOT EXISTS idx_system_prompt_sections_is_active ON system_prompt_sections(is_active);

-- Insert default API guidance
INSERT INTO api_guidance (api_name, display_name, description, when_to_use, when_not_to_use, priority, is_active, created_at, updated_at)
VALUES
    (
        'ise',
        'Cisco ISE External RESTful Services (ERS) API',
        'Full ISE ERS API covering network access devices, internal users and identity groups, endpoints and profiling, authorization policy elements, TrustSec SGTs and matrices, guest and sponsor portals, certificates, Active Directory join points, and deployment nodes',
        'Use for all ISE configuration and inventory work: onboarding network devices, managing identities and endpoints, editing policy elements, running TrustSec queries, and administering guest access.',
        'Not applicable — this is the only API available for ISE operations. Note that ERS covers configuration only; live session and posture data comes from the ISE Monitoring (MnT) API, which is not part of this server.',
        10, TRUE, NOW(), NOW()
    )
ON CONFLICT (api_name) DO NOTHING;

-- Insert resource-family guidance for the ERS resource groups
INSERT INTO category_guidance (api_name, category_name, display_name, description, when_to_use, related_categories, priority, is_active, created_at, updated_at)
VALUES
    (
        'ise', 'network', 'Network Access Devices',
        'Network device (NAD) inventory and grouping: network devices with their RADIUS and TACACS+ shared secrets, network device groups, external RADIUS servers, and RADIUS/TACACS server sequences.',
        'Use for onboarding switches, WLCs and firewalls as RADIUS or TACACS+ clients, organising them into device groups, and reviewing shared-secret and CoA configuration.',
        '["policy", "trustsec"]', 10, TRUE, NOW(), NOW()
    ),
    (
        'ise', 'identity', 'Identities & Endpoints',
        'Internal users, identity groups, identity store sequences, endpoints and endpoint groups, endpoint certificates, profiler profiles, and REST ID stores.',
        'Use for creating or auditing internal accounts, managing endpoint MAC identities and their group assignment, and reviewing profiling results.',
        '["policy", "guest"]', 20, TRUE, NOW(), NOW()
    ),
    (
        'ise', 'policy', 'Authorization Policy Elements',
        'Policy building blocks referenced by authorization rules: authorization profiles, downloadable ACLs, allowed protocol services, certificate profiles and templates, and filter policies.',
        'Use for reviewing or editing what ISE returns on a successful authorization — VLAN, dACL, SGT and reauthentication settings — and which EAP methods are permitted.',
        '["identity", "network", "trustsec"]', 30, TRUE, NOW(), NOW()
    ),
    (
        'ise', 'trustsec', 'TrustSec (SGT, SGACL & SXP)',
        'Security Group Tags, SGACLs, the egress policy matrix and its cells, SG mappings and mapping groups, SXP connections, local bindings and VPNs, and the CTS query endpoints.',
        'Use for reading or changing segmentation policy: tag definitions, matrix cells, IP-to-SGT mappings, and SXP peering. CTS query operations are served on TCP 9063 rather than the ERS port.',
        '["policy", "network"]', 40, TRUE, NOW(), NOW()
    ),
    (
        'ise', 'guest', 'Guest & Sponsor Access',
        'Guest users and guest types, sponsor groups and sponsor group members, guest locations and SSIDs, SMTP and SMS notification settings, and the guest, sponsor, hotspot, BYOD and self-registration portals.',
        'Use for creating and managing guest accounts through their lifecycle (create, suspend, reinstate, notify), and for reviewing portal and sponsor configuration.',
        '["identity"]', 50, TRUE, NOW(), NOW()
    ),
    (
        'ise', 'threat', 'Adaptive Network Control & Threat',
        'ANC policies and ANC endpoint actions (quarantine, port bounce, shutdown, reauthenticate), and threat and vulnerability clearing.',
        'Use to contain a compromised endpoint by applying an ANC policy to its MAC address, and to clear the containment once remediation is complete.',
        '["identity", "policy"]', 60, TRUE, NOW(), NOW()
    ),
    (
        'ise', 'deployment', 'Deployment, Certificates & Directories',
        'ISE deployment nodes and node services, deployment and telemetry info, system certificates, Active Directory join points and domain operations, LDAP identity sources, pxGrid nodes and settings, and support bundles.',
        'Use for checking deployment topology and node personas, reviewing certificate and directory integration, and collecting support bundles.',
        '["identity"]', 70, TRUE, NOW(), NOW()
    )
ON CONFLICT (api_name, category_name) DO NOTHING;

-- Insert default system prompt sections
INSERT INTO system_prompt_sections (section_name, section_order, title, content, is_active, created_at, updated_at)
VALUES
    (
        'overview',
        10,
        'API Overview',
        'You are working with the Cisco Identity Services Engine (ISE) External RESTful Services (ERS) API. Operations are grouped by resource family: network (network access devices and device groups), identity (internal users, identity groups, endpoints, profiling), policy (authorization profiles, dACLs, allowed protocols), trustsec (SGTs, SGACLs, egress matrix, SXP), guest (guest users, sponsor groups, portals), threat (ANC quarantine actions), and deployment (nodes, certificates, Active Directory). ERS covers configuration only — live session, posture and authentication logs come from the ISE Monitoring (MnT) API, which this server does not expose.',
        TRUE, NOW(), NOW()
    ),
    (
        'api_selection',
        20,
        'API Selection Guidelines',
        'When selecting operations: 1) Identify the resource family for the task. 2) Prefer the getByName operation when the user gives you a name — most ERS resources expose one, and it saves a list-and-filter round trip. 3) Otherwise list with a filter and read the resource UUID from the result before calling an operation that takes an {id} path parameter. 4) Check category guidance for the resource family, and consider workflows for common multi-step tasks. 5) Validate required path, query and body parameters before calling.',
        TRUE, NOW(), NOW()
    ),
    (
        'identifiers',
        25,
        'Working with ISE Identifiers',
        'Almost every ERS resource is addressed by a UUID in its {id} path parameter, not by its display name. Resolve a name first: call the resource getByName operation where one exists, or list with filter=name.EQUALS.<value> and read the id from the SearchResult. Endpoints are the exception — they are keyed by MAC address, and ANC actions take the MAC directly. Never guess a UUID.',
        TRUE, NOW(), NOW()
    ),
    (
        'pagination',
        27,
        'Pagination & Filtering',
        'Get-All operations return an ERS SearchResult: a total count, a resources array of name/id/link summaries, and a nextPage link. The default page size is 20 and the maximum is 100, so set size and page explicitly when enumerating. Narrow results with filter using the documented syntax field.OPERATOR.value (for example name.CONTAINS.branch or macAddress.EQUALS.00:11:22:33:44:55); each operation description lists the fields it supports. The summary entries carry only name, id and link — call getById to see the full object.',
        TRUE, NOW(), NOW()
    ),
    (
        'write_operations',
        28,
        'Create, Update & Delete',
        'ERS request bodies wrap the object in a single resource key, for example {"NetworkDevice": {...}}; send the body exactly in that shape. A successful create returns 201 with an empty body and the new UUID in the Location header. PUT replaces the whole object, so read the current resource with getById first and send it back with your changes applied, otherwise unset fields are cleared; use PATCH where the resource supports it to change fields in isolation.',
        TRUE, NOW(), NOW()
    ),
    (
        'best_practices',
        30,
        'Best Practices',
        'Follow these practices: 1) Verify prerequisites before configuration changes — a network device needs its group hierarchy and shared secret ready, and an authorization profile needs its dACL to exist first. 2) Use read operations to validate state before and after changes. 3) For destructive operations (deleting a network device, an identity group, or a matrix cell), confirm the target name and UUID with the user first. 4) Treat RADIUS and TACACS+ shared secrets, and any password field, as sensitive — never echo them back. 5) Break complex tasks into logical steps. 6) Surface the ISE ERSResponse error message verbatim; it names the field that failed validation. 7) Log all configuration changes for audit purposes.',
        TRUE, NOW(), NOW()
    )
ON CONFLICT (section_name) DO NOTHING;
