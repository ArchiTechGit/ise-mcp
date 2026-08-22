# Available Operations — Cisco ISE

**Total operations**: 1,007 across 33 APIs
**Status**: All operations available as MCP tools

| Group | Specs | Operations | Tool prefix |
|-------|------:|-----------:|-------------|
| ERS | 1 | 395 | `ise_` |
| Open API | 30 | 590 | `ise_oa_<category>_` |
| Monitoring (MnT) | 1 | 20 | `ise_mnt_` |
| API Service | 1 | 2 | `ise_apisvc_` |

Every operation in every registered spec becomes one MCP tool. ERS declares no
`operationId`, so its names are synthesized from each operation's tag and
summary; every Open API and MnT operation declares one and it is used verbatim.
See [API_PATHS.md](API_PATHS.md) for naming and routing details.

> **1,007 tools is far more than an MCP client will surface** (typically
> 40–128). Tool profiles are how you scope a user to a workable set — there is
> one per category, and the Administrator role bypasses filtering entirely.
> See [Tool Profiles](#tool-profiles).

## Operation Summary by HTTP Method

| Method | Count | Access |
|--------|------:|--------|
| GET    | 443   | ✅ Always available (read-only) |
| POST   | 233   | 🔒 Requires edit mode |
| PUT    | 185   | 🔒 Requires edit mode |
| DELETE | 117   | 🔒 Requires edit mode |
| PATCH  | 29    | 🔒 Requires edit mode |

With edit mode disabled (the default), 443 operations are reachable and 564 are
blocked.

> ISE uses `PUT` more than most APIs because many actions — applying an ANC
> policy, suspending a guest, joining an AD domain, deploying SG mappings — are
> modelled as `PUT` on an action path rather than as `POST`.

## Operations by Resource Family

| Family | Resources | Operations | Purpose |
|--------|----------:|-----------:|---------|
| Guest | 17 | 90 | Guest users and types, sponsor groups, portals |
| Identity | 14 | 74 | Internal users, identity groups, endpoints, profiling, REST ID stores |
| TrustSec | 15 | 69 | SGTs, SGACLs, egress matrix, SG mappings, SXP |
| Network | 8 | 58 | Network access devices, device groups, RADIUS/TACACS+ servers |
| Deployment | 14 | 53 | Nodes, certificates, Active Directory, LDAP, pxGrid, support bundles |
| Policy | 7 | 40 | Authorization profiles, dACLs, allowed protocols, certificate profiles |
| Threat | 3 | 11 | ANC policies and endpoint containment |

The API Service sits outside these families — it configures ISE's API surface
rather than any access-control object:

| Tool | Method | Purpose |
|------|--------|---------|
| `ise_apisvc_retrieveOpenAPIStatus` | GET | Is the Open API enabled, on the PAN and on the PSNs? |
| `ise_apisvc_updateOpenAPIStatus` | POST | Enable or disable it (`papIsEnabled`, `psnsIsEnabled`) |

> Both need **Super Admin**, not the ERS Admin group the rest of this server
> uses. And `updateOpenAPIStatus` widens the deployment's API attack surface —
> read the status first and confirm intent before changing it.

### Largest resources

| Resource | Family | Operations |
|----------|--------|-----------:|
| `guestuser` | Guest | 18 |
| `activedirectory` | Deployment | 16 |
| `adminuser` | Identity | 12 |
| `endpoint` | Identity | 11 |
| `ldap` | Deployment | 11 |
| `internaluser` | Identity | 10 |
| `networkdevice` | Network | 10 |
| `restidstore` | Identity | 10 |

## The Standard CRUD Shape

Most ERS resources expose the same five to seven operations, which is why the
tool names are so predictable:

| Tool | Method | Path | Notes |
|------|--------|------|-------|
| `ise_<resource>_getAll` | GET | `/<resource>/` | Paginated `SearchResult`; supports `filter`, `page`, `size`, `sortasc`, `sortdsc` |
| `ise_<resource>_getById` | GET | `/<resource>/{id}` | Full object |
| `ise_<resource>_getByName` | GET | `/<resource>/name/{name}` | Where the resource supports it — saves a list-and-filter round trip |
| `ise_<resource>_create` | POST | `/<resource>/` | 201 with the new UUID in `Location` |
| `ise_<resource>_update` | PUT | `/<resource>/{id}` | **Replaces** the whole object |
| `ise_<resource>_patch` | PATCH | `/<resource>/{id}` | Changes named fields only |
| `ise_<resource>_delete` | DELETE | `/<resource>/{id}` | |

Learning this shape once covers roughly two thirds of the tool surface.

## Key Operation Categories

### Network Access Devices

```
ise_networkdevice_getAll          ise_networkdevice_create
ise_networkdevice_getById         ise_networkdevice_update
ise_networkdevice_getByName       ise_networkdevice_updateByName
ise_networkdevice_delete          ise_networkdevice_deleteByName
ise_networkdevice_patch           ise_networkdevice_patchByName

ise_networkdevicegroup_getAll     ise_networkdevicegroup_create
ise_networkdevicegroup_getById    ise_networkdevicegroup_getByName
ise_networkdevicegroup_update     ise_networkdevicegroup_delete
```

A network device carries its IP list, device group membership, and its RADIUS
and/or TACACS+ shared secrets. Device groups must exist before a device can
reference them.

### Identities and Endpoints

```
ise_internaluser_getAll           ise_internaluser_create
ise_internaluser_getByName        ise_internaluser_updateByName
ise_internaluser_patch            ise_internaluser_delete

ise_identitygroup_getAll          ise_identitygroup_getByName
ise_identitygroup_create          ise_identitygroup_update

ise_endpoint_getAll               ise_endpoint_create
ise_endpoint_getByName            ise_endpoint_getById
ise_endpoint_update               ise_endpoint_delete
ise_endpoint_register             ise_endpoint_deRegister
ise_endpoint_getRejectedEndpoints ise_endpoint_releaseRejectedEndpoint

ise_profilerprofile_getAll        ise_profilerprofile_getById
```

> Endpoints are keyed by **MAC address**, not UUID — `ise_endpoint_getByName`
> takes the MAC.

### Authorization Policy Elements

```
ise_authorizationprofile_getAll   ise_authorizationprofile_getByName
ise_authorizationprofile_getById  ise_authorizationprofile_create
ise_authorizationprofile_update   ise_authorizationprofile_patch

ise_downloadableacl_getAll        ise_downloadableacl_getById
ise_downloadableacl_create        ise_downloadableacl_update

ise_allowedprotocols_getAll       ise_allowedprotocols_getByName
ise_allowedprotocols_getById      ise_allowedprotocols_update
```

These are the building blocks authorization rules reference — what ISE returns
on a successful authorization (VLAN, dACL, SGT, reauthentication) and which EAP
methods are permitted. The rules that combine them live in the ISE policy UI,
not in ERS.

### TrustSec

```
ise_sgt_getAll                    ise_sgt_create
ise_sgt_getById                   ise_sgt_update              ise_sgt_delete

ise_sgacl_getAll                  ise_sgacl_create
ise_sgacl_getById                 ise_sgacl_update            ise_sgacl_delete

ise_egressmatrixcell_getAll       ise_egressmatrixcell_create
ise_egressmatrixcell_getById      ise_egressmatrixcell_update
ise_egressmatrixcell_cloneCell    ise_egressmatrixcell_setAllCellsStatus
ise_egressmatrixcell_clearAllMatrixCells

ise_sgmapping_getAll              ise_sgmapping_deployByID
ise_sgmapping_deployAll           ise_sgmapping_deployStatus

ise_sxpconnections_getAll         ise_sxplocalbindings_getAll
```

The egress matrix binds a source SGT, a destination SGT, and an SGACL into one
cell. CTS query operations (`ise_ctsmatrix_trustSecQuery*`,
`ise_ctsenvdata_trustSecQuery*`, `ise_sgacls_trustSecQuery*`) are served on
**port 9063** and are routed there automatically.

### Guest and Sponsor Access

```
ise_guestuser_getAll              ise_guestuser_create
ise_guestuser_getByName           ise_guestuser_updateByName
ise_guestuser_suspendByName       ise_guestuser_reinstateByName
ise_guestuser_approve             ise_guestuser_deny
ise_guestuser_email               ise_guestuser_sms
ise_guestuser_resetpassword       ise_guestuser_changeSponsorPassword

ise_guesttype_getAll              ise_sponsorgroup_getAll
ise_portal_getAll                 ise_portal_getById
```

`ise_guestuser_*` is the largest single resource in the API at 18 operations,
because the guest lifecycle (create, approve, notify, suspend, reinstate,
delete) is exposed both by ID and by name.

### Adaptive Network Control (Threat Containment)

```
ise_ancpolicy_getAll              ise_ancpolicy_getByName
ise_ancpolicy_create              ise_ancpolicy_update       ise_ancpolicy_delete

ise_ancendpoint_getAll            ise_ancendpoint_getById
ise_ancendpoint_apply             ise_ancendpoint_clear
```

An ANC policy names an action — `QUARANTINE`, `PORTBOUNCE`, `SHUTDOWN`, or
`REAUTHENTICATE`. `ise_ancendpoint_apply` binds it to an endpoint MAC address;
`ise_ancendpoint_clear` releases it. These are the highest-impact write
operations in the API: applying one can drop a device off the network
immediately.

### Deployment, Certificates and Directories

```
ise_node_getAll                   ise_node_getByName          ise_node_getById
ise_deploymentinfo_getAllInfo     ise_sessionservicenode_getAll
ise_pxgridnode_getAll             ise_telemetryinfo_getAll

ise_activedirectory_getAllJoinPoints    ise_activedirectory_getJoinPointDetails
ise_activedirectory_joinADomain         ise_activedirectory_leaveADomain
ise_activedirectory_getGroupsByDomain   ise_activedirectory_getUserGroups
ise_activedirectory_isUserAMemberOfGroups

ise_ldap_getAll                   ise_idstoresequence_getAll
ise_systemcertificate_create      ise_supportbundle_create
```

## Open API Categories

Thirty specs, 590 operations. The two that matter most close gaps ERS cannot:

| Category | Tools | Covers |
|----------|------:|--------|
| `ise_oa_trustsec_*` | 139 | Classification policy, security groups, egress/ingress matrices, SXP, dictionaries |
| `ise_oa_policy_*` | 138 | **Policy sets and authorization rules** — network access and device admin, conditions, dictionaries, global exceptions |
| `ise_oa_exim_*` | 29 | Bulk import and export |
| `ise_oa_rbac_*` | 28 | Admin RBAC catalog: menu and data access permissions |
| `ise_oa_deploy_*` | 24 | Node registration, personas, node groups, PAN failover |
| `ise_oa_certs_*` | 22 | System and trusted certs, CSRs, import and export |
| `ise_oa_upgrade_*` | 20 | Upgrade staging, prepare, proceed, rollback |
| `ise_oa_alarms_*`, `ise_oa_prometheus_*` | 32 | Alarms and Prometheus AlertManager integration |
| `ise_oa_5g_*` | 16 | 5G user equipment and subscribers |
| 21 further categories | 152 | Webhooks, licensing, backup, repository, patch, pxGrid, profiler, OIDC, MFA, IPSec, Duo, and more |

`ise_oa_policy_*` is what finally answers "which rule granted this access?" —
ERS holds only the policy *elements* those rules reference.

## Live State — Monitoring (MnT)

`ise_mnt_*`, 20 operations (17 read). The only API here that reports what is
happening now rather than what is configured:

```
ise_mnt_getActiveSessionCount      ise_mnt_getActiveSessionList
ise_mnt_getPostureCount            ise_mnt_getProfilerCount
ise_mnt_getSessionsByMac           ise_mnt_getSessionsByUsername
```

> These must target a Monitoring node, not a dedicated PAN. Verify the responses
> come back as JSON — the older `/admin/API/mnt/` interface returned XML only,
> and while this spec is OpenAPI, a non-JSON body is passed through as
> `{"data": ..., "status_code": ...}` rather than failing.

## Tool Profiles

One profile per category, derived from the registry at startup rather than
hand-written in SQL, so a newly registered spec produces its profile
automatically:

| Profile | Count | Scope |
|---------|------:|-------|
| `Full Access` | — | **No filtering.** What the Administrator role points at |
| `Open API - <category>` | 30 | One per Open API spec |
| `ERS - <family>` | 7 | ERS split by resource family — one 395-tool profile would not narrow anything |
| `Monitoring - Live Sessions` | 1 | The 20 MnT operations |
| `Open API Enablement` | 1 | The 2 API Service operations |
| `Read-Only Analyst` | 1 | Every GET across every API (443) |
| `Network Operator`, `Infrastructure Viewer`, `Troubleshooting Only` | 3 | Cross-cutting, pre-seeded |

47 profiles in total. Assign one per user, or per role.

> **`max_tools` is advisory** — nothing truncates a tool list to it. The single
> value with behaviour attached is `0`, which *combined with an empty operation
> list* is the sentinel for Full Access. Auto-created profiles are therefore
> given a non-zero `max_tools` equal to their own size, so a profile that
> somehow ended up empty could never be mistaken for Full Access and silently
> grant all 1,007 tools.

## Usage Examples

### Example 1: List network devices

```
"List all network devices in ISE"
-> ise_networkdevice_getAll { "size": 100 }
```

### Example 2: Find one device by name

```
"Show me the config for branch-sw-01"
-> ise_networkdevice_getByName { "name": "branch-sw-01" }
```

### Example 3: Filter a large collection

```
"Find every network device whose name contains 'branch'"
-> ise_networkdevice_getAll { "filter": "name.CONTAINS.branch", "size": 100 }
```

### Example 4: Look up an endpoint by MAC

```
"What does ISE know about 00:11:22:33:44:55?"
-> ise_endpoint_getByName { "name": "00:11:22:33:44:55" }
```

### Example 5: Review TrustSec segmentation

```
"Show me the TrustSec egress matrix"
-> ise_sgt_getAll               (resolve tag names and values)
-> ise_sgacl_getAll             (resolve ACL names)
-> ise_egressmatrixcell_getAll  (the cells that bind them)
```

### Example 6: Check whether the Open API is enabled

```
"Is the ISE Open API turned on?"
-> ise_apisvc_retrieveOpenAPIStatus {}
   -> { "papIsEnabled": false, "psnsIsEnabled": true }
```

### Example 7: Onboard a device (edit mode required)

```
-> ise_networkdevicegroup_getAll     (confirm the group hierarchy)
-> ise_networkdevice_create {
     "body": { "NetworkDevice": {
       "name": "branch-sw-01",
       "profileName": "Cisco",
       "coaPort": 1700,
       "NetworkDeviceIPList": [{ "ipaddress": "10.1.1.1", "mask": 32 }],
       "authenticationSettings": { "radiusSharedSecret": "..." }
     }}}
-> ise_networkdevice_getByName       (confirm what ISE stored)
```

## Tool Name Format

ERS (names synthesized, because the spec declares no `operationId`):

```
ise_<resource>_<action>
```

- `ise` — the API's `tool_prefix`, from `api_registry.APIS["ise"]`
- `<resource>` — the operation's OpenAPI tag, e.g. `networkdevice`, `sgt`, `guestuser`
- `<action>` — the summary in camelCase, e.g. `getAll`, `getById`, `create`, `suspendByName`

API Service (names taken from the spec):

```
ise_apisvc_<operationId>
```

Names are at most 55 characters, well inside the 64-character MCP limit, and
are stable across restarts because they are derived deterministically from the
spec. The derived name is stored on `api_endpoints.tool_name` so RBAC and tool
profiles match exactly what the server advertises.

## Read-Only vs Edit Mode

### Read-Only Mode (Default)

- All 443 GET operations available
- 564 write operations blocked with a clear error naming edit mode
- Safe for inventory, audit, and policy review

### Edit Mode (`EDIT_MODE_ENABLED=true`, or via the Security page)

- All 1,007 operations available
- Every operation recorded in the audit log
- Enable deliberately, and prefer granting write access per role rather than
  globally

> Treat ANC operations, `delete` on any resource, `ise_apisvc_updateOpenAPIStatus`,
> and anything touching a shared secret as high-impact. The seeded guidance instructs Claude to confirm
> the target with you first.

## Complete Operation List

The full inventory lives in the database once the server has started:

```bash
# Every tool name, with its method and path
docker compose exec ise_mcp_postgres psql -U mcp_user -d ise_mcp -c \
  "SELECT tool_name, http_method, path FROM api_endpoints ORDER BY tool_name;"

# Count by method
docker compose exec ise_mcp_postgres psql -U mcp_user -d ise_mcp -c \
  "SELECT http_method, count(*) FROM api_endpoints GROUP BY http_method ORDER BY 2 DESC;"
```

Seeded descriptions for every operation — including its parameters and request
body fields — are in
[../src/config/migrations/008_seed_tool_descriptions.sql](../src/config/migrations/008_seed_tool_descriptions.sql),
regenerated with:

```bash
python scripts/generate_tool_descriptions.py
```

## API Documentation

- [Cisco ISE API Reference — ERS](https://developer.cisco.com/docs/identity-services-engine/)
- [API_PATHS.md](API_PATHS.md) — routing, naming, authentication, and response conventions
- [API_GUIDANCE_SYSTEM.md](API_GUIDANCE_SYSTEM.md) — customizing tool descriptions and workflows
