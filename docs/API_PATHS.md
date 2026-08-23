# Cisco ISE API Path Reference

## API Base Paths

Thirty-three ISE APIs are registered in
[../src/core/api_registry.py](../src/core/api_registry.py), which supplies the
base path and tool-name prefix for each.

| Group | Specs | Operations | Base path | Port | Tool prefix |
|-------|------:|-----------:|-----------|-----:|-------------|
| ERS | 1 | 395 | `/ers/config` | 9060 | `ise_` |
| Open API | 30 | 590 | *(none — paths are absolute)* | 443 | `ise_oa_<category>_` |
| Monitoring (MnT) | 1 | 20 | `/admin/API/mnt` | 443 | `ise_mnt_` |
| API Service | 1 | 2 | *(none)* | 443 | `ise_apisvc_` |
| **Total** | **33** | **1,007** | | | |

The thirty Open API specs are declared as a table in the registry rather than
written out one by one, so adding a spec is a single row. Three of them need
their base path set explicitly — see
[Base paths that the specs do not state](#base-paths-that-the-specs-do-not-state).

> The `servers` entries in the Open API specs are Cisco lab addresses
> (`https://172.23.9.91:443`, `https://10.56.60.25:443`, …) and are ignored
> entirely. The base URL always comes from the deployment credentials.

### Base paths that the specs do not state

27 of the 30 Open API specs write absolute paths (`/api/v1/policy/...`), so
their base path is empty. Three do not:

| Spec | Paths look like | Spec's `servers` path | Registered base path |
|------|-----------------|----------------------|----------------------|
| `deployment.yaml` | `/deployment/node/` | *(none declared)* | `/api/v1` |
| `upgrade.yaml` | `/upgrade/stage` | `/v1` | `/api/v1` |
| `5G.yaml` | `/fiveg/user-equipment` | `/v1` | `/api/v1` |

`/api/v1` is used because every sibling spec is served there, but the specs
themselves disagree — two claim a bare `/v1`. **Verify these three against a
live PAN.** If the guess is wrong, their 60 operations will uniformly 404 while
the other 947 tools work, which is a confusing failure to diagnose after the
fact.

An empty base path is distinct from an *unknown* API, which falls back to the
ERS root; [../src/middleware/auth.py](../src/middleware/auth.py) tests for
`None` rather than falsiness so that `""` is honoured.

### ISE API Service — what it is and is not

The API Service spec covers exactly two operations:

| Tool | Method | Path |
|------|--------|------|
| `ise_apisvc_retrieveOpenAPIStatus` | GET | `/admin/API/apiService/get` |
| `ise_apisvc_updateOpenAPIStatus` | POST | `/admin/API/apiService/update` |

It reads and sets whether the ISE **Open API** is enabled — `papIsEnabled` for
the Policy Administration node, `psnsIsEnabled` for the Policy Service nodes.

It is the *switch*, not the surface. The Open API itself — policy sets,
authorization rules, certificates, backup, patch, repository, licensing — lives
at `/api/v1/...` and is **not currently loaded into this server**. To add it,
export the spec from `https://{ise}/api/swagger-ui/index.html` and register it
as a third API. Its operations need Super Admin rights, and so do these two.

Its paths are absolute from the server root, so its base path is empty. That is
distinct from an *unknown* API, which falls back to the ERS root — see
[../src/middleware/auth.py](../src/middleware/auth.py).

The spec declares its server as:

```yaml
servers:
  - url: https://{server}:{port}/ers/config
    description: Append /ctsapi/v2 or /ctsapi/v3 to above URL while accessing CTS APIs
    variables:
      server:
        default: localhost
      port:
        description: The port no for CTS APIs is 9063 and for other APIs it is 443
        default: '443'
```

Paths inside the spec are written relative to that root (`/networkdevice/`, not
`/ers/config/networkdevice/`), so `AuthMiddleware.execute_request()` prepends
the `/ers/config` base path before dispatching.

> **Port caveat:** the spec's `443` default is not what a real deployment uses.
> ERS answers on **TCP 9060**, so `ISE_HOST_URL` must include the port —
> `https://ise.example.com:9060`. See [Two Ports, One API](#two-ports-one-api).

## Resource Families

There is one API, but its 78 resources group into seven families by purpose.
The family is a documentation and guidance concept — it is how
`category_guidance` is seeded — not a path prefix.

| Family | Resources | Operations | GET | POST | PUT | PATCH | DELETE |
|--------|----------:|-----------:|----:|-----:|----:|------:|-------:|
| Guest | 17 | 90 | 35 | 12 | 26 | 5 | 12 |
| Identity | 14 | 74 | 29 | 8 | 17 | 10 | 10 |
| TrustSec | 15 | 69 | 22 | 21 | 17 | 0 | 9 |
| Network | 8 | 58 | 23 | 8 | 9 | 9 | 9 |
| Deployment | 14 | 53 | 28 | 4 | 18 | 0 | 3 |
| Policy | 7 | 40 | 18 | 5 | 6 | 5 | 6 |
| Threat | 3 | 11 | 5 | 1 | 4 | 0 | 1 |
| **Total** | **78** | **395** | **160** | **59** | **97** | **29** | **50** |

**Example endpoints:**
- List network devices: `GET /ers/config/networkdevice`
- Get a network device by name: `GET /ers/config/networkdevice/name/{name}`
- Get a network device by ID: `GET /ers/config/networkdevice/{id}`
- Create a network device: `POST /ers/config/networkdevice/`
- Look up an endpoint by MAC: `GET /ers/config/endpoint/name/{name}`
- Quarantine an endpoint: `PUT /ers/config/ancendpoint/apply`
- TrustSec matrix query: `POST /ers/config/ctsapi/v2/ctsmatrix/` (port 9063)

## No operationIds — Names Are Synthesized

This is the most important naming detail in the ERS spec: it declares **no
`operationId` anywhere**. (The API Service spec does declare them, and those
are used verbatim — synthesis is a fallback, not a policy. See
[Naming across two specs](#naming-across-two-specs).) Every operation identifies itself only by an OpenAPI
tag and a terse summary, and those summaries repeat heavily — 59 operations are
called `Get-All` and 58 are called `Get-By-Id`.

[../src/core/tool_naming.py](../src/core/tool_naming.py) therefore synthesizes
both an operation ID and a tool name, deterministically, from the spec:

```
tag:      networkdevice
summary:  Get-All
          |
          v
operation_id:  networkdevice_getAll
tool_name:     ise_networkdevice_getAll
```

Names resolve in three escalating passes so the common case stays short and
only genuinely ambiguous operations pick up extra detail:

1. `{resource}_{action}` — unique for 383 of the 395 operations
2. append the path segments that differ — this is what separates
   `/ctsmatrix/` from `/ctsapi/v2/ctsmatrix/` and `/ctsapi/v3/ctsmatrix/`:

   | Path | Tool name |
   |------|-----------|
   | `POST /ctsmatrix/` | `ise_ctsmatrix_trustSecQuery` |
   | `POST /ctsapi/v2/ctsmatrix/` | `ise_ctsmatrix_trustSecQuery_ctsapi_v2` |
   | `POST /ctsapi/v3/ctsmatrix/` | `ise_ctsmatrix_trustSecQuery_ctsapi_v3` |

3. append a digest of `METHOD path` — never reached with the current spec, but
   keeps the mapping total if Cisco adds a genuinely identical pair

Because names cannot be reconstructed by string concatenation in SQL, the
derived tool name is stored on `api_endpoints.tool_name` (migration 011) and is
what RBAC, tool profiles, and the operations picker all match against.

### Naming across two specs

`build_operation_ids()` prefers a declared `operationId` over a synthesized one,
so each spec gets the better of the two:

| Spec | Declares operationId? | Operation ID | Tool name |
|------|----------------------|--------------|-----------|
| ERS | no — synthesized from tag + summary | `networkdevice_getAll` | `ise_networkdevice_getAll` |
| Open API (all 610 ops) | yes — used verbatim | `getNetworkAccessPolicySets` | `ise_oa_policy_getNetworkAccessPolicySets` |

The Open API names its operations descriptively, and 22 of the 610 exceed the
64-character limit once prefixed. Those are shortened in stages — abbreviate
known long words, then drop a word that already appeared, then truncate with a
digest — so they stay readable rather than being cut mid-word:

```
getCommonPolicyClassificationAttributesByDictionaryNameByAttributeName   (86 chars prefixed)
  -> ise_oa_trustsec_getCommonPolicyClassifAttrsByDictNameByAttrName     (63)
```

Each API carries its own `tool_prefix`, so two specs can never collide even if
they name an operation identically. Adding an API therefore never renames the
tools of an existing one — which matters, because those names are already
seeded into the database.

## Three Ports, One Base URL

ISE does not serve everything on one port, so the client routes by path:

| Path | Port | Setting |
|------|-----:|---------|
| `/ers/config/...` | 9060 | from `ISE_HOST_URL` |
| `/ers/config/ctsapi/...` | 9063 | `ISE_CTS_PORT` |
| `/api/...` (Open API) | 443 | `ISE_ADMIN_PORT` |
| `/admin/API/...` (API Service, MnT) | 443 | `ISE_ADMIN_PORT` |

The last two are both the ISE API gateway.

[../src/services/ise_api.py](../src/services/ise_api.py) handles this in
`_port_for_path()`: the base URL supplies the default, and a path belonging to
another family has its port rewritten before dispatch.

```
tool call            ise_ctsmatrix_trustSecQuery_ctsapi_v2
spec path            /ctsapi/v2/ctsmatrix/
+ base path          /ers/config/ctsapi/v2/ctsmatrix/
+ base URL           https://ise.example.com:9060/ers/config/ctsapi/v2/ctsmatrix/
+ CTS port rewrite   https://ise.example.com:9063/ers/config/ctsapi/v2/ctsmatrix/
```

```
tool call            ise_apisvc_retrieveOpenAPIStatus
spec path            /admin/API/apiService/get
+ base path          (empty — already absolute from the root)
+ base URL           https://ise.example.com:9060/admin/API/apiService/get
+ admin port rewrite https://ise.example.com:443/admin/API/apiService/get
```

Set `ISE_CTS_PORT=0` or `ISE_ADMIN_PORT=0` to disable a rewrite when a reverse
proxy serves the families on one port.

## Implementation in MCP Server

### Path Construction Flow

```
1. Tool call arrives:            ise_networkdevice_getById { "id": "abc-123" }
2. Look up operation:            GET /networkdevice/{id}
3. Substitute path parameters:   GET /networkdevice/abc-123
4. Route query parameters:       only names declared `in: query` are forwarded
5. Prepend base path:            /ers/config/networkdevice/abc-123
6. Prepend cluster base URL:     https://ise.example.com:9060/ers/config/networkdevice/abc-123
7. Rewrite port for /ctsapi/:    (not applicable here)
```

Step 4 matters: arguments are matched against the parameters the spec actually
declares. Anything unrecognized is logged and dropped rather than being
appended blindly to the query string, which would otherwise send request-body
fields as query parameters when a caller forgot to nest them under `body`.

### Request Bodies

ERS wraps every payload in a single resource key. Creating a network device
means posting:

```json
{
  "NetworkDevice": {
    "name": "branch-sw-01",
    "profileName": "Cisco",
    "coaPort": 1700,
    "NetworkDeviceIPList": [{ "ipaddress": "10.1.1.1", "mask": 32 }],
    "authenticationSettings": { "radiusSharedSecret": "..." }
  }
}
```

The MCP tool advertises that shape as its `body` input schema rather than an
opaque object, so the wrapper key and required fields are visible to the caller.
Schemas are pruned of ERS boilerplate first (`"example": null`, `title`
duplicating the property name), and prose enumerations are repaired:

```yaml
# as written in the spec — the type is wrong
keyInputFormat:
  type: object
  description: "allowed values:ASCII,HEXADECIMAL"
```
```json
// as advertised by the tool
{ "type": "string", "description": "allowed values:ASCII,HEXADECIMAL",
  "enum": ["ASCII", "HEXADECIMAL"] }
```

## Authentication

ERS uses **HTTP Basic authentication on every request** — there is no session
token to obtain, refresh, or expire. Two headers are always sent:

```
Accept: application/json
Content-Type: application/json
```

Without the `Accept` header ERS replies with XML; without `Content-Type` it
rejects a body with `415 Unsupported Media Type`.

`ISEAPIClient.authenticate()` exists to validate stored credentials up front and
to give the web UI a meaningful "Test Connection" result. It probes:

1. `GET /ers/config/op/systemconfig/iseversion` — returns the running ISE
   version, which is worth surfacing on the health page
2. `GET /ers/config/networkdevice?size=1` — fallback for builds where the
   version endpoint is unavailable

### Prerequisites on ISE

1. **Administration > System > Settings > API Settings > ERS Settings** on the
   Primary PAN -> enable **ERS (Read/Write)**
2. The account must belong to the **ERS Admin** group (read/write) or the
   **ERS Operator** group (read-only)

## Response Conventions

| Status | ERS behaviour | What the MCP tool returns |
|--------|---------------|---------------------------|
| 200 | JSON body | The parsed body |
| 201 | **Empty body**; new UUID in the `Location` header | `{"status": "created", "location": ..., "id": ...}` |
| 204 | Empty body (update/delete) | `{"status": "success", "status_code": 204}` |
| 4xx/5xx | `ERSResponse` naming the field that failed | The error message, surfaced verbatim |

A create therefore never returns the object it made — read it back with the
matching `getById` or `getByName` operation to confirm what ISE stored.

## Pagination and Filtering

`Get-All` operations return an ERS `SearchResult`:

```json
{
  "SearchResult": {
    "total": 143,
    "resources": [{ "id": "...", "name": "branch-sw-01", "link": { "href": "..." } }],
    "nextPage": { "href": "...?page=2&size=100" }
  }
}
```

- Default page size is **20**, maximum is **100** — set `size` and `page`
  explicitly when enumerating.
- `resources` entries carry only `id`, `name`, and `link`. Call `getById` for
  the full object.
- Filter with `filter=field.OPERATOR.value`, for example
  `name.CONTAINS.branch` or `mac.EQUALS.00:11:22:33:44:55`. Each operation's
  description lists the fields it supports.

## Common Issues and Solutions

### Issue: Connection refused or timeout

**Cause:** the URL is missing the ERS port. ERS does not answer on 443.

**Fix:** set the deployment URL to `https://ise.example.com:9060`.

### Issue: 401 Unauthorized

**Causes:**
- The ERS service is not enabled on the Primary PAN
- The account is not in an ERS Admin or ERS Operator group
- Wrong credentials

Basic auth is replayed on every request, so a 401 is never transient — the
client fails fast rather than retrying.

### Issue: XML response instead of JSON

**Cause:** the `Accept: application/json` header was dropped. The client always
sends it; if you see XML, you are calling ISE directly rather than through the
MCP server.

### Issue: 415 Unsupported Media Type

**Cause:** a request body was sent without `Content-Type: application/json`, or
the body is missing its resource wrapper key.

### Issue: TrustSec operation returns connection refused

**Cause:** the CTS port rewrite is disabled (`ISE_CTS_PORT=0`) but ISE is still
serving CTS on 9063.

**Fix:** leave `ISE_CTS_PORT=9063` unless a proxy genuinely unifies both ports.

### Issue: API Service operation returns 401 or 403

**Cause:** the API Service under `/admin/API/` requires **Super Admin**, not the
ERS Admin group that the rest of this server needs. An ERS-only account reaches
every ERS operation and is rejected here.

### Issue: PUT cleared fields you did not send

**Cause:** ERS `PUT` replaces the whole object.

**Fix:** read the current resource with `getById`, apply your change to that
document, and send the whole thing back — or use `PATCH` where the resource
supports it.

## Testing API Paths

### Manual Testing

```bash
ISE=https://ise.example.com:9060
AUTH=ersadmin:YourPassword

# 1. Confirm ERS is reachable and the account works
curl -sk -u "$AUTH" -H 'Accept: application/json' \
  "$ISE/ers/config/op/systemconfig/iseversion"

# 2. List network devices (first page)
curl -sk -u "$AUTH" -H 'Accept: application/json' \
  "$ISE/ers/config/networkdevice?size=100"

# 3. Look up one by name
curl -sk -u "$AUTH" -H 'Accept: application/json' \
  "$ISE/ers/config/networkdevice/name/branch-sw-01"

# 4. TrustSec query — note the different port
curl -sk -u "$AUTH" -H 'Accept: application/json' \
  -H 'Content-Type: application/json' -X POST -d '{}' \
  "https://ise.example.com:9063/ers/config/ctsapi/v2/ctsmatrix/"
```

### Automated Testing

```bash
# Verify the spec loads and every tool builds
docker compose exec ise_mcp_mcp_server python -c "
import asyncio
from src.core.mcp_server import ISEMCP
mcp = ISEMCP()
asyncio.run(mcp.load_api('ise'))
tools = mcp.list_all_tools()
print(len(tools), 'tools;', len({t.name for t in tools}), 'unique names')
"
```

## References

- [Cisco ISE API Reference — ERS](https://developer.cisco.com/docs/identity-services-engine/)
- [../src/core/api_registry.py](../src/core/api_registry.py) — base path definition
- [../src/core/tool_naming.py](../src/core/tool_naming.py) — operation ID and tool name synthesis
- [../src/core/api_loader.py](../src/core/api_loader.py) — spec loading, `$ref` resolution, schema cleanup
- [../src/services/ise_api.py](../src/services/ise_api.py) — authentication and CTS port routing
- [../src/middleware/auth.py](../src/middleware/auth.py) — base path prefixing and response handling
- [AVAILABLE_OPERATIONS.md](AVAILABLE_OPERATIONS.md) — full operation inventory
