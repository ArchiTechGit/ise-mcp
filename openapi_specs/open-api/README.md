# ISE Open API specifications

Downloaded from Cisco DevNet on 2026-08-22:
`https://pubhub.devnetcloud.com/media/identity-services-engine-api-v1/docs/endpoints/Open-API/`

30 specs, 590 operations. **Not yet registered** in `src/core/api_registry.py` —
see the note on tool count below.

## Registering one

Every operation in every spec declares an `operationId`, so
`tool_naming.build_operation_ids()` uses those verbatim; no synthesis needed.
What each spec needs is the right `base_path`:

| base_path | Specs | Why |
|-----------|-------|-----|
| `""` (none) | 27 of 30 | Paths are already absolute — `/api/v1/policy/...` |
| **verify** | `5G.yaml`, `upgrade.yaml` | Paths are relative (`/fiveg/...`, `/upgrade/...`) and the spec declares server path `/v1`, which conflicts with the `/api/v1` the other specs use |
| **verify** | `deployment.yaml` | Paths are relative (`/deployment/node/`) and the spec declares no server path at all |

The three marked *verify* must be checked against a live PAN before enabling —
guessing between `/v1` and `/api/v1` would produce 60 tools that all 404.

The declared `servers` entries are Cisco lab addresses
(`https://172.23.9.91:443`, `https://10.56.60.25:443`, …) and are ignored: the
base URL always comes from the deployment credentials in the database.

## Largest specs

| Spec | Operations | Covers |
|------|-----------:|--------|
| `TrustSec.yaml` | 139 | Classification policy, SGT/SGACL, egress matrix, SXP — a newer, wider surface than ERS TrustSec |
| `policy.yaml` | 138 | **Policy sets and authorization rules**, both network-access and device-admin — the gap ERS cannot fill |
| `exim.yaml` | 29 | Bulk import/export |
| `rbac.yaml` | 28 | Admin RBAC catalog (has circular `$ref`s — resolved to `{}` with a warning) |
| `deployment.yaml` | 24 | Node registration, personas, PAN HA |
| `certificates.yaml` | 22 | System/trusted certs, CSRs, import/export |

## Before enabling all of them

30 specs = 590 tools, on top of the 397 already registered: **987 total**.
MCP clients typically surface 40–128 tools, and `docs/CRITICAL_FIXES.md` records
that tool-count pressure is why the tool-profile mechanism exists. Enabling
everything at once would make tool selection markedly worse, not better.

Prefer registering the specs that close a real capability gap, and scope the
rest behind tool profiles.
