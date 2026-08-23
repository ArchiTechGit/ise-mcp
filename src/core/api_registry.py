"""API Registry for the Cisco Identity Services Engine (ISE) ERS API."""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class APIDefinition:
    """Definition of an ISE API."""

    name: str
    display_name: str
    spec_file: str
    base_path: str
    description: str
    #: Prefix for every MCP tool name generated from this spec. Distinct per
    #: API so two specs can never collide on a shared operation name.
    tool_prefix: str = "ise"
    enabled: bool = True


class APIRegistry:
    """Registry for ISE API definitions.

    Cisco ISE exposes its External RESTful Services (ERS) API from a single
    root — ``/ers/config`` — described by one specification
    (``ERS_APIs.yaml``). Within it the operations group into resource families:

      - identity      — internal users, identity groups, endpoints, endpoint groups
      - network       — network devices, device groups, RADIUS and TACACS servers
      - policy        — authorization profiles, allowed protocols, downloadable ACLs
      - trustsec      — SGTs, SGACLs, the egress matrix, SXP bindings, CTS queries
      - guest         — guest users, guest types, sponsor groups, portals
      - deployment    — ISE nodes, certificates, Active Directory, support bundles

    ERS itself listens on TCP 9060; the TrustSec (CTS) subset of the same
    specification is served on TCP 9063, and the API Service lives on the admin
    HTTPS port (443). :class:`src.services.ise_api.ISEAPIClient` routes each
    request to the right port automatically.
    """

    #: The ISE Open API, one entry per published specification. Columns are
    #: (registry key, spec file, category slug, display name, description).
    #:
    #: Paths in these specs are absolute — ``/api/v1/policy/...`` — so their base
    #: path is empty. The four exceptions are listed in :data:`_BASE_PATH_OVERRIDES`.
    _OPEN_API_SPECS = (
        ("policy", "policy.yaml", "Policy",
         "Policy sets and rules for network access and device admin, conditions, dictionaries, and global exceptions"),
        ("trustsec", "TrustSec.yaml", "TrustSec",
         "Classification policy, security groups, egress and ingress matrices, SXP, and TrustSec dictionaries"),
        ("exim", "exim.yaml", "Import / Export",
         "Bulk import and export of configuration objects"),
        ("rbac", "rbac.yaml", "Admin RBAC Catalog",
         "Administrator RBAC catalog: menu and data access permissions, admin groups, and RBAC policies"),
        ("deploy", "deployment.yaml", "Deployment",
         "Node registration and deregistration, personas and services, node groups, and PAN failover"),
        ("certs", "certificates.yaml", "Certificates",
         "System and trusted certificates, certificate signing requests, and certificate import and export"),
        ("upgrade", "upgrade.yaml", "Upgrade",
         "Deployment upgrade staging, prepare, proceed and rollback, plus patch install and rollback"),
        ("5g", "5G.yaml", "5G",
         "5G user equipment and subscriber registration"),
        ("alarms", "alarms.yaml", "Alarms",
         "Alarm definitions, thresholds, notification settings, and alarm acknowledgement"),
        ("prometheus", "prometheus-alertmanager.yaml", "Prometheus AlertManager",
         "Prometheus AlertManager integration: alerts, silences, and receiver configuration"),
        ("pxgriddirect", "pxgrid-direct.yaml", "pxGrid Direct",
         "pxGrid Direct connectors and sync schedules for pulling external context into ISE"),
        ("webhooks", "webhooks.yaml", "Webhooks",
         "Outbound webhook definitions and delivery configuration"),
        ("license", "licensing.yaml", "Licensing",
         "Smart licensing registration, tier entitlement, and license consumption"),
        ("duo", "duo-identity-sync.yaml", "Duo IdentitySync",
         "Duo multi-factor identity synchronisation configuration"),
        ("endpoints", "endpoints.yaml", "Endpoints (Open API)",
         "Endpoint create, update and delete including bulk operations - the newer counterpart to the ERS endpoint resource"),
        ("profiler", "ise-profiler.yaml", "Profiler",
         "Profiler feed service, profiling policies, and endpoint profiling configuration"),
        ("ipsec", "ipsec.yaml", "IPSec",
         "IPSec tunnel configuration between ISE nodes and network devices"),
        ("oidc", "oidc.yaml", "OIDC",
         "OpenID Connect identity provider configuration"),
        ("mfa", "mfa.yaml", "MFA",
         "Multi-factor authentication provider configuration"),
        ("backup", "BackupRestore.yaml", "Backup and Restore",
         "Configuration backup and restore, backup schedules, and restore status"),
        ("repo", "Repository.yaml", "Repository",
         "Repository configuration for backups, upgrades and support bundles, and repository file listing"),
        ("patch", "patch-hot-patch.yaml", "Patch and Hot Patch",
         "Patch and hot patch install, rollback, and installed-patch listing"),
        ("sgtreserve", "api-sgt-reservation.yaml", "SGT Reservation",
         "Reservation of security group tag ranges for external clients"),
        ("customattr", "custom-attributes.yaml", "Custom Attributes",
         "Custom endpoint and user attribute definitions"),
        ("dataconnect", "data-connect.yaml", "Data Connect",
         "Data Connect ODBC access configuration for external reporting"),
        ("pxgridcloud", "pxgrid-cloud.yaml", "pxGrid Cloud",
         "pxGrid Cloud connectivity and enablement"),
        ("syssettings", "System-Settings.yaml", "System Settings",
         "System-level settings including proxy and FIPS configuration"),
        ("endpointrepl", "endpoint-replication.yaml", "Endpoint Replication",
         "Endpoint replication settings between deployments"),
        ("lsd", "lsd-settings.yaml", "LSD Settings",
         "Local Store and Deliver settings"),
        ("task", "task-service.yaml", "Task Service",
         "Status of long-running asynchronous tasks started by other Open API operations"),
    )

    #: Specs whose paths are *not* absolute. Everything else uses "".
    #:
    #: The Monitoring API declares its own server path. The other three write
    #: relative paths and either declare a bare ``/v1`` server (5G, upgrade) or
    #: none at all (deployment); ``/api/v1`` is used because every sibling spec
    #: is served there. **Verify these three against a live PAN** - if the guess
    #: is wrong, their 60 operations will uniformly 404.
    _BASE_PATH_OVERRIDES = {
        "5g": "/api/v1",
        "upgrade": "/api/v1",
        "deploy": "/api/v1",
    }

    APIS: Dict[str, APIDefinition] = {
        "ise": APIDefinition(
            name="ise",
            display_name="Cisco Identity Services Engine (ERS)",
            spec_file="ERS_APIs.yaml",
            base_path="/ers/config",
            description=(
                "Full ISE External RESTful Services API — network devices, internal "
                "users and identity groups, endpoints and profiling, authorization "
                "policy elements, TrustSec SGTs and matrices, guest and sponsor "
                "portals, certificates, Active Directory, and deployment nodes"
            ),
            tool_prefix="ise",
            enabled=True,
        ),
        "apiservice": APIDefinition(
            name="apiservice",
            display_name="Cisco ISE API Service (Open API enablement)",
            spec_file="open-api.yaml",
            # Paths in this spec are absolute from the server root
            # (/admin/API/apiService/...), so nothing is prepended.
            base_path="",
            description=(
                "Reads and sets whether the ISE Open API is enabled, on the "
                "Policy Administration node and on Policy Service nodes. This is "
                "the switch that exposes the /api/v1 Open API surface"
            ),
            tool_prefix="ise_apisvc",
            enabled=True,
        ),
        "mnt": APIDefinition(
            name="mnt",
            display_name="Cisco ISE Monitoring (MnT)",
            spec_file="monitoring/monitoring-open-api.yaml",
            # Declared by the spec's own servers entry.
            base_path="/admin/API/mnt",
            description=(
                "Live session state: active session counts and lists, posture and "
                "profiler counts, session lookup by MAC, IP or username, and "
                "session deletion. This is the only API here that reports what is "
                "happening now rather than what is configured. Operations must "
                "target a Monitoring node, not a dedicated PAN"
            ),
            tool_prefix="ise_mnt",
            enabled=True,
        ),
    }

    @classmethod
    def get_api(cls, name: str) -> Optional[APIDefinition]:
        """Get API definition by name.

        Args:
            name: API name

        Returns:
            APIDefinition or None if not found
        """
        return cls.APIS.get(name)

    @classmethod
    def get_enabled_apis(cls) -> List[APIDefinition]:
        """Get list of enabled APIs."""
        return [api for api in cls.APIS.values() if api.enabled]

    @classmethod
    def get_all_apis(cls) -> List[APIDefinition]:
        """Get list of all APIs."""
        return list(cls.APIS.values())

    @classmethod
    def enable_api(cls, name: str) -> bool:
        """Enable an API. Returns True if the API exists."""
        api = cls.get_api(name)
        if api:
            api.enabled = True
            return True
        return False

    @classmethod
    def disable_api(cls, name: str) -> bool:
        """Disable an API. Returns True if the API exists."""
        api = cls.get_api(name)
        if api:
            api.enabled = False
            return True
        return False

    @classmethod
    def get_base_path_for_api(cls, api_name: str) -> Optional[str]:
        """Get the base path an API is served under.

        Args:
            api_name: API name

        Returns:
            Base path string or None if API not found
        """
        api = cls.get_api(api_name)
        return api.base_path if api else None

def _register_open_api_specs() -> None:
    """Add one :class:`APIDefinition` per Open API spec to the registry.

    Built from :data:`APIRegistry._OPEN_API_SPECS` rather than written out
    thirty times, so a new spec is one row rather than a block.
    """
    for key, spec_file, display, description in APIRegistry._OPEN_API_SPECS:
        APIRegistry.APIS[f"oa_{key}"] = APIDefinition(
            name=f"oa_{key}",
            display_name=f"Cisco ISE Open API — {display}",
            spec_file=f"open-api/{spec_file}",
            base_path=APIRegistry._BASE_PATH_OVERRIDES.get(key, ""),
            description=description,
            tool_prefix=f"ise_oa_{key}",
            enabled=True,
        )


_register_open_api_specs()
