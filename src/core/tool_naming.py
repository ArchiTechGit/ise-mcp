"""Deterministic MCP tool naming for Cisco ISE ERS operations.

The ISE ERS specification declares no ``operationId`` anywhere — all 395
operations identify themselves only by a tag (``networkdevice``, ``sgt``,
``guestuser``, ...) and a short summary (``Get-All``, ``Get-By-Id``,
``Create``, ...). Those summaries repeat heavily: 59 operations are called
``Get-All``. Names therefore have to be synthesized from tag + summary, with
the request path used to break the few remaining ties.

The result for every operation is a pair:

  operation_id  ``networkdevice_getAll``       (spec-level identity)
  tool_name     ``ise_networkdevice_getAll``   (what MCP advertises)

Synthesis is a fallback, not a policy. A spec that *does* declare
``operationId`` — as the ISE API Service spec does — has its own IDs used
verbatim, because a name Cisco chose is more meaningful than one derived from a
tag. Each API also carries its own tool-name prefix, so the two specs cannot
collide even if they name an operation the same way.

Both halves are pure functions of the specification, so they stay stable across
restarts and match what is seeded into the database. This module is the single
source of truth: the MCP server, the RBAC endpoint sync, and the tool
description generator all derive names from here.
"""

import hashlib
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

MAX_TOOL_NAME_LEN = 64

#: Prefix applied to every tool name, mirroring the ``{api}_{operation}``
#: convention used by the sibling MCP servers.
TOOL_NAME_PREFIX = "ise"

#: Fallback verb per HTTP method, used when an operation carries no summary.
_METHOD_VERBS = {
    "GET": "get",
    "POST": "create",
    "PUT": "update",
    "DELETE": "delete",
    "PATCH": "patch",
    "HEAD": "head",
    "OPTIONS": "options",
}

#: Human-readable phrasing for the ERS action verbs. ISE summaries are terse
#: ("Get-All", "Patch"), which is too thin for a model choosing between 395
#: tools, so the tool description expands them against the resource tag.
_ACTION_PHRASES = {
    "getAll": "List all {resource} resources",
    "getById": "Get one {resource} resource by ID",
    "getByName": "Get one {resource} resource by name",
    "create": "Create a new {resource} resource",
    "update": "Update the {resource} resource with the given ID",
    "updateById": "Update the {resource} resource with the given ID",
    "updateByName": "Update the {resource} resource with the given name",
    "delete": "Delete the {resource} resource with the given ID",
    "deleteById": "Delete the {resource} resource with the given ID",
    "deleteByName": "Delete the {resource} resource with the given name",
    "patch": "Partially update the {resource} resource with the given ID",
    "patchByName": "Partially update the {resource} resource with the given name",
    "trustSecQuery": "Run a TrustSec query against {resource}",
}


#: ERS resources grouped by purpose. The families are how ``category_guidance``
#: is organised in the web UI and how the default tool profiles are scoped;
#: every one of the spec's 78 tags appears in exactly one family.
RESOURCE_FAMILIES: Dict[str, Tuple[str, ...]] = {
    "network": (
        "networkdevice", "networkdevicegroup", "externalradiusserver",
        "radiusserversequence", "tacacsexternalservers", "tacacsserversequence",
        "tacacscommandsets", "tacacsprofile",
    ),
    "identity": (
        "internaluser", "identitygroup", "endpoint", "endpointgroup", "endpointcert",
        "profilerprofile", "idstoresequence", "restidstore", "restidstoreattribute",
        "restidstoredeviceattribute", "restidstoregroup", "restidstorepredefinedregex",
        "restidstoresettings", "adminuser",
    ),
    "policy": (
        "authorizationprofile", "downloadableacl", "allowedprotocols",
        "certificateprofile", "certificatetemplate", "filterpolicy", "nspprofile",
    ),
    "trustsec": (
        "sgt", "sgacl", "sgacls", "egressmatrixcell", "sgmapping", "sgmappinggroup",
        "sgtvnvlan", "sxpconnections", "sxplocalbindings", "sxpvpns", "ctsmatrix",
        "ctsenvdata", "reportconfig", "acibindings", "acisettings",
    ),
    "guest": (
        "guestuser", "guesttype", "guestlocation", "guestssid",
        "guestsmtpnotificationsettings", "sponsorgroup", "sponsorgroupmember",
        "smsprovider", "portal", "portaltheme", "portalglobalsetting", "byodportal",
        "hotspotportal", "mydeviceportal", "selfregportal", "sponsoredguestportal",
        "sponsorportal",
    ),
    "threat": ("ancendpoint", "ancpolicy", "threat"),
    "deployment": (
        "node", "deploymentinfo", "sessionservicenode", "pxgridnode", "pxgridsettings",
        "systemcertificate", "activedirectory", "adresourcereservation", "ldap",
        "service", "supportbundle", "supportbundledownload", "supportbundlestatus",
        "telemetryinfo",
    ),
}

#: Human-readable label per resource family, used to name the ERS tool profiles.
FAMILY_DISPLAY: Dict[str, str] = {
    "network": "Network Access Devices",
    "identity": "Identities & Endpoints",
    "policy": "Authorization Policy Elements",
    "trustsec": "TrustSec (SGT, SGACL & SXP)",
    "guest": "Guest & Sponsor Access",
    "threat": "Adaptive Network Control",
    "deployment": "Deployment & Directories",
}

_RESOURCE_TO_FAMILY: Dict[str, str] = {
    resource: family
    for family, resources in RESOURCE_FAMILIES.items()
    for resource in resources
}


def family_for_operation_id(operation_id: str) -> Optional[str]:
    """Return the resource family an operation ID belongs to.

    Args:
        operation_id: Operation ID such as ``networkdevice_getAll``.

    Returns:
        The family name (``"network"``, ``"identity"``, ...), or None when the
        resource is not one the families cover.
    """
    resource, _, _ = operation_id.partition("_")
    return _RESOURCE_TO_FAMILY.get(resource)


def resources_for_families(*families: str) -> Set[str]:
    """Return every resource name belonging to the given families."""
    return {r for f in families for r in RESOURCE_FAMILIES.get(f, ())}


#: Long words that appear in ISE Open API operation IDs. The Open API names its
#: operations descriptively — ``getCommonPolicyClassificationAttributesByDictionary
#: NameByAttributeName`` is a real one — and 22 of the 610 exceed the 64-character
#: MCP tool name limit once prefixed. Abbreviating known words keeps those
#: readable instead of truncating them mid-word.
ABBREVIATIONS: Dict[str, str] = {
    "Classification": "Classif",
    "Authentication": "Authn",
    "Authorization": "Authz",
    "Configuration": "Config",
    "Dictionaries": "Dicts",
    "Dictionary": "Dict",
    "Attributes": "Attrs",
    "Attribute": "Attr",
    "Exceptions": "Excs",
    "Exception": "Exc",
    "Conditions": "Conds",
    "Condition": "Cond",
    "Connections": "Conns",
    "Connection": "Conn",
    "Connectors": "Connectrs",
    "Connector": "Connectr",
    "Equipment": "Equip",
    "Subscriber": "Subscr",
    "Reservation": "Reserv",
    "Replication": "Repl",
    "Certificates": "Certs",
    "Certificate": "Cert",
    "Repository": "Repo",
    "Statistics": "Stats",
    "Summary": "Summ",
    "Network": "Net",
    "Virtual": "Virt",
    "Default": "Deflt",
    "Global": "Glob",
}


def _split_camel(name: str) -> List[str]:
    """Split a camelCase or PascalCase identifier into its words.

    ``getNetworkAccessPolicySet`` becomes
    ``["get", "Network", "Access", "Policy", "Set"]``. Runs of capitals such as
    ``CSR`` in ``getCSRs`` are kept together.
    """
    return re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|^[a-z0-9]+|[a-z0-9]+", name)


def _abbreviate(name: str) -> str:
    """Replace known long words in a camelCase identifier with shorter forms."""
    return "".join(ABBREVIATIONS.get(w, w) for w in _split_camel(name))


def _drop_repeated_words(name: str) -> str:
    """Drop a word that already appeared earlier in the identifier.

    Open API IDs sometimes restate a noun — ``...ByDictionaryNameByAttributeName``
    repeats ``By`` and ``Name`` — and dropping the later copy costs little
    meaning. The leading verb is always kept.
    """
    words = _split_camel(name)
    if not words:
        return name

    kept = [words[0]]
    seen = {words[0].lower()}
    for w in words[1:]:
        key = w.lower()
        if key in seen:
            continue
        seen.add(key)
        kept.append(w)
    return "".join(kept)


def _camel_case(text: str) -> str:
    """Turn an ERS summary into a camelCase action token.

    ``"Get-By-Id"`` becomes ``getById`` and ``"Join a domain with all nodes"``
    becomes ``joinADomainWithAllNodes``.

    Args:
        text: Summary text as written in the specification.

    Returns:
        A camelCase token, or an empty string if nothing usable remains.
    """
    words = [w for w in re.split(r"[^0-9A-Za-z]+", text) if w]
    if not words:
        return ""

    head, *tail = words
    return head[0].lower() + head[1:] + "".join(w[0].upper() + w[1:] for w in tail)


def build_action(summary: Optional[str], method: str) -> str:
    """Derive the action half of an operation ID.

    Args:
        summary: OpenAPI ``summary`` for the operation, if any.
        method: Upper-case HTTP method, used when the summary is missing.

    Returns:
        A camelCase action such as ``getAll``, ``create`` or ``deleteByName``.
    """
    return _camel_case(summary or "") or _METHOD_VERBS.get(method.upper(), method.lower())


def build_resource(operation: Dict[str, Any]) -> str:
    """Derive the resource half of an operation ID.

    The first OpenAPI tag names the ERS resource. When an operation is
    untagged, the first literal path segment is used instead.

    Args:
        operation: Raw operation dictionary, including ``tags`` and ``path``.

    Returns:
        The resource name, e.g. ``networkdevice``.
    """
    tags = operation.get("tags") or []
    if tags and isinstance(tags[0], str) and tags[0].strip():
        return tags[0].strip()

    for segment in _literal_segments(operation.get("path", "")):
        return segment

    return "ers"


def _literal_segments(path: str) -> List[str]:
    """Return the path segments that are not ``{placeholders}``."""
    return [seg for seg in path.strip("/").split("/") if seg and not seg.startswith("{")]


def _qualifier_segments(path: str, resource: str, action: str) -> List[str]:
    """Path segments that could disambiguate two operations sharing a name.

    Segments already represented by the resource or the action carry no new
    information, so ``/ancendpoint/apply`` contributes nothing beyond
    ``ancendpoint_apply``, while ``/ctsapi/v2/ctsmatrix/`` contributes
    ``ctsapi`` and ``v2``.

    Args:
        path: Request path from the specification.
        resource: Resource half of the operation ID.
        action: Action half of the operation ID.

    Returns:
        Ordered, de-duplicated qualifier segments.
    """
    known = {resource.lower()} | {w.lower() for w in re.findall(r"[A-Za-z0-9]+", action)}
    qualifiers: List[str] = []

    for segment in _literal_segments(path):
        key = segment.lower()
        if key in known:
            continue
        known.add(key)
        qualifiers.append(segment)

    return qualifiers


def _sanitize(raw: str) -> str:
    """Reduce an identifier to the characters MCP tool names allow."""
    name = re.sub(r"[^0-9A-Za-z_-]+", "_", raw)
    name = re.sub(r"_+", "_", name)
    return name.strip("_")


def _digest(text: str, length: int = 6) -> str:
    """Return a short, stable hex digest, used only to break hard ties."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def build_operation_ids(operations: Sequence[Dict[str, Any]]) -> List[str]:
    """Assign a unique operation ID to every operation in the specification.

    Names are resolved in three escalating passes so that the common case stays
    short and readable, and only genuinely ambiguous operations pick up extra
    detail:

      1. ``{resource}_{action}`` — unique for 383 of the 395 ERS operations
      2. append path qualifiers — separates ``/ctsmatrix/`` from
         ``/ctsapi/v2/ctsmatrix/`` and ``/ctsapi/v3/ctsmatrix/``
      3. append a digest of ``METHOD path`` — never reached today, but keeps
         the mapping total if Cisco adds a genuinely identical pair

    Args:
        operations: Raw operations in specification order. Each needs
            ``method``, ``path``, ``tags`` and ``summary``.

    Returns:
        Operation IDs positionally aligned with ``operations``.
    """
    bases: List[Tuple[str, str, str]] = []
    base_counts: Dict[str, int] = {}

    for operation in operations:
        declared = operation.get("operationId")
        if isinstance(declared, str) and declared.strip():
            # The spec named it; use that name rather than inventing one.
            base = _sanitize(declared)
            resource, action = "", ""
        else:
            resource = build_resource(operation)
            action = build_action(operation.get("summary"), operation.get("method", "GET"))
            base = _sanitize(f"{resource}_{action}")
        bases.append((base, resource, action))
        base_counts[base] = base_counts.get(base, 0) + 1

    operation_ids: List[str] = []
    taken: Set[str] = set()

    for operation, (base, resource, action) in zip(operations, bases):
        name = base

        # Path qualifiers only help a synthesized name; a declared operationId
        # that still collides goes straight to the digest.
        if base_counts[base] > 1 and resource:
            qualifiers = _qualifier_segments(operation.get("path", ""), resource, action)
            if qualifiers:
                name = _sanitize(f"{base}_{'_'.join(qualifiers)}")

        if name in taken:
            identity = f"{operation.get('method', '')} {operation.get('path', '')}"
            name = f"{name}_{_digest(identity)}"

        taken.add(name)
        operation_ids.append(name)

    return operation_ids


def build_tool_name(operation_id: str, prefix: str = TOOL_NAME_PREFIX) -> str:
    """Build the MCP tool name advertised for an operation ID.

    Args:
        operation_id: Operation ID from :func:`build_operation_ids`.
        prefix: Per-API prefix from ``APIDefinition.tool_prefix``. Keeping this
            distinct per API is what stops two specs colliding on a shared
            operation name.

    Returns:
        A name matching ``^[a-zA-Z0-9_-]{1,64}$``, e.g.
        ``ise_networkdevice_getAll``.
    """
    name = _sanitize(f"{prefix}_{operation_id}")
    if len(name) <= MAX_TOOL_NAME_LEN:
        return name

    # Shorten in escalating stages so only genuinely oversized names lose
    # detail, and they lose it in the least destructive order available.
    for shorten in (_abbreviate, lambda n: _drop_repeated_words(_abbreviate(n))):
        candidate = _sanitize(f"{prefix}_{shorten(operation_id)}")
        if len(candidate) <= MAX_TOOL_NAME_LEN:
            return candidate

    # Last resort: truncate, with a digest of the original ID so the result
    # stays unique and stable.
    suffix = _digest(operation_id)
    return f"{candidate[: MAX_TOOL_NAME_LEN - len(suffix) - 1]}_{suffix}"


def build_tool_name_map(
    operation_ids: Iterable[str], prefix: str = TOOL_NAME_PREFIX
) -> Dict[str, str]:
    """Map operation IDs to tool names.

    Args:
        operation_ids: Operation IDs, which are already unique.
        prefix: Per-API prefix from ``APIDefinition.tool_prefix``.

    Returns:
        Dict of ``{operation_id: tool_name}``.
    """
    return {
        operation_id: build_tool_name(operation_id, prefix)
        for operation_id in operation_ids
    }


def describe_operation(operation: Dict[str, Any]) -> str:
    """Build a one-line, model-friendly headline for an operation.

    ISE summaries alone ("Get-All", "Patch") do not say what is being acted on,
    so the resource is folded in: ``List all networkdevice resources``.

    Args:
        operation: Normalized operation dictionary from the API loader.

    Returns:
        A single sentence with no trailing period.
    """
    summary = (operation.get("summary") or "").strip()

    # A spec that declares operationIds is generally one that writes real
    # summaries too, so the summary stands on its own.
    if operation.get("operationId") and summary:
        return summary

    resource = build_resource(operation)
    action = build_action(summary, operation.get("method", "GET"))

    phrase = _ACTION_PHRASES.get(action)
    if phrase:
        return phrase.format(resource=resource)

    if summary:
        return f"{summary} — {resource}"

    return f"{operation.get('method', 'GET')} {operation.get('path', '')}"
