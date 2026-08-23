# ISE Monitoring (MnT) Open API specification

Downloaded from Cisco DevNet on 2026-08-22:
`https://pubhub.devnetcloud.com/media/identity-services-engine-api-v1/docs/endpoints/Monitoring-Open-API/`

`monitoring-open-api.yaml` — 20 operations (17 GET, 3 write), all with
`operationId`s. **Not yet registered** in `src/core/api_registry.py`.

This is the live-state API: active session counts and lists, posture and
profiler counts, session lookup by MAC/IP/username, and session deletion. It
answers the questions ERS structurally cannot — "is this endpoint connected
right now?", "why did it fail?" — which makes it the highest-value addition
here despite its size.

- **Base path**: `/admin/API/mnt` (declared by the spec's own `servers` entry)
- **Port**: the admin HTTPS port. `ISEAPIClient._port_for_path()` already routes
  `/admin/API/` to `ISE_ADMIN_PORT`, so no client change is needed.
- **Node**: these operations must target an MnT node, not a dedicated PAN.
- **Response format**: verify JSON works. The older `/admin/API/mnt/` interface
  returned XML only; this spec being OpenAPI suggests JSON, but confirm against
  a live box before relying on it — `AuthMiddleware` returns
  `{"data": ..., "status_code": ...}` for a non-JSON body rather than failing.
