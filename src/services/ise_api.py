"""Cisco Identity Services Engine (ISE) ERS API client."""

import logging
from typing import Any, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

import httpx

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

#: Cheap, well-known ERS endpoint used to validate credentials. It returns the
#: running ISE version, which is worth surfacing on the health page.
ISE_VERSION_PATH = "/ers/config/op/systemconfig/iseversion"

#: Fallback probe for deployments where the version endpoint is unavailable —
#: every ERS admin can read the network device collection.
ISE_PROBE_PATH = "/ers/config/networkdevice"

#: ERS returns XML unless JSON is asked for explicitly, so these headers are
#: sent on every request rather than only on writes.
ISE_JSON_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}

#: Path fragment identifying the TrustSec (CTS) subset of the ERS spec, which
#: ISE serves on a different port from the rest of ERS.
CTS_PATH_MARKER = "/ctsapi/"

#: Path prefixes served by the ISE API gateway on the admin HTTPS port rather
#: than the ERS port: the Open API surface (``/api/v1/...``) and the admin
#: family (``/admin/API/...``, which covers the API Service and MnT).
GATEWAY_PATH_PREFIXES = ("/api/", "/admin/API/")


class ISEAPIClient:
    """Client for authenticating and making requests to the ISE ERS API.

    ISE ERS uses HTTP Basic authentication on every request — there is no
    session token to obtain or refresh — so :meth:`authenticate` exists only to
    validate the stored credentials up front and to give the web UI a
    meaningful "test connection" result.

    Two ISE-specific behaviours are handled here:

    * **Content negotiation.** ERS answers with XML unless ``Accept:
      application/json`` is present, and rejects a body without
      ``Content-Type: application/json`` with a 415.
    * **Per-family ports.** ISE does not serve everything on one port. ERS
      listens on TCP 9060 and its TrustSec operations under ``/ctsapi/`` on TCP
      9063, while the API gateway serves the Open API (``/api/v1/...``) and the
      admin family (``/admin/API/...``, covering the API Service and MnT) on the
      admin HTTPS port (443). Requests are re-pointed by path automatically; set
      ``ISE_CTS_PORT`` or ``ISE_ADMIN_PORT`` to 0 to disable a rewrite when a
      proxy unifies the ports.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        verify_ssl: bool = False,
    ):
        """Initialize the ISE API client.

        Args:
            base_url: ISE Primary PAN base URL, e.g. ``https://ise.example.com:9060``
            username: ERS admin username (must belong to an ERS Admin or ERS
                Operator group)
            password: ERS admin password
            verify_ssl: Whether to verify TLS certificates
        """
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.settings = get_settings()

        self.authenticated = False
        self.ise_version: Optional[str] = None

        self.client = httpx.AsyncClient(
            verify=verify_ssl,
            auth=(username, password),
            timeout=httpx.Timeout(self.settings.api_timeout),
            follow_redirects=True,
        )

    def _port_for_path(self, path: str) -> Optional[int]:
        """Return the port ISE serves ``path`` on, or None to keep the URL's own.

        Args:
            path: API path beginning at the server root.

        Returns:
            The port to route to, or None when the base URL's port already
            applies (the ERS case) or the rewrite has been disabled.
        """
        if path.startswith(GATEWAY_PATH_PREFIXES):
            return self.settings.ise_admin_port or None
        if CTS_PATH_MARKER in path:
            return self.settings.ise_cts_port or None
        return None

    def _build_url(self, path: str) -> str:
        """Build the absolute URL for an ISE path, routed to the right port.

        Args:
            path: API path beginning at the server root, e.g.
                ``/ers/config/networkdevice``.

        Returns:
            Absolute URL, with the port switched where the path belongs to an
            API family ISE serves elsewhere (see :meth:`_port_for_path`).
        """
        suffix = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{suffix}"

        port = self._port_for_path(suffix)
        if port is None:
            return url

        parts = urlsplit(url)
        if parts.port == port:
            return url

        netloc = f"{parts.hostname}:{port}"
        if parts.username:
            credentials = parts.username
            if parts.password:
                credentials = f"{credentials}:{parts.password}"
            netloc = f"{credentials}@{netloc}"

        logger.debug("Routing %s to port %d", suffix, port)
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    async def authenticate(self) -> bool:
        """Validate the stored ERS credentials.

        Returns:
            True if ISE accepted the credentials, False otherwise.
        """
        for path in (ISE_VERSION_PATH, ISE_PROBE_PATH):
            try:
                response = await self.client.get(
                    self._build_url(path),
                    headers=ISE_JSON_HEADERS,
                    params={"size": 1} if path == ISE_PROBE_PATH else None,
                )
            except Exception as exc:
                logger.error("ISE authentication error against %s: %s", path, exc)
                return False

            if response.status_code == 200:
                self.authenticated = True
                if path == ISE_VERSION_PATH:
                    self.ise_version = self._extract_version(response)
                logger.info(
                    "ISE authentication successful%s",
                    f" (version {self.ise_version})" if self.ise_version else "",
                )
                return True

            if response.status_code in (401, 403):
                logger.error(
                    "ISE rejected the credentials (%s). Confirm the ERS service is "
                    "enabled and the account belongs to an ERS Admin group.",
                    response.status_code,
                )
                return False

            # 404 on the version endpoint just means an older ISE build; fall
            # through and try the probe path instead.
            logger.warning(
                "ISE returned %s for %s, trying the next probe", response.status_code, path
            )

        logger.error("ISE authentication failed: no probe endpoint responded successfully")
        return False

    @staticmethod
    def _extract_version(response: httpx.Response) -> Optional[str]:
        """Pull the ISE version string out of an ``iseversion`` response."""
        try:
            payload = response.json()
        except Exception:
            return None

        version = (
            payload.get("OperationResult", {})
            .get("resultValue", [])
            if isinstance(payload, dict) else []
        )
        for entry in version:
            if isinstance(entry, dict) and entry.get("name") == "ISE VERSION":
                return entry.get("value")
        return None

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Make an authenticated request to the ISE ERS API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            path: API path, e.g. ``/ers/config/networkdevice``
            params: Optional query parameters
            json_data: Optional JSON request body
            headers: Optional additional headers

        Returns:
            httpx.Response

        Raises:
            RuntimeError: If the stored credentials are rejected
            httpx.HTTPStatusError: On non-2xx responses after retries
        """
        if not self.authenticated:
            if not await self.authenticate():
                raise RuntimeError("Failed to authenticate with ISE")

        url = self._build_url(path)
        request_headers = {**ISE_JSON_HEADERS, **(headers or {})}

        max_retries = self.settings.api_retry_attempts
        last_exception: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                response = await self.client.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    json=json_data,
                    headers=request_headers,
                )

                # Basic auth is replayed on every request, so a 401 means the
                # credentials themselves are no longer valid — retrying will
                # not help.
                if response.status_code == 401:
                    self.authenticated = False
                    raise RuntimeError(
                        "ISE rejected the stored credentials (401). Verify the ERS "
                        "admin account and that the ERS service is enabled."
                    )

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as exc:
                last_exception = exc
                if attempt < max_retries - 1:
                    logger.warning(
                        "Request failed (attempt %d/%d): %s", attempt + 1, max_retries, exc
                    )
                    continue
                raise

            except RuntimeError:
                raise

            except Exception as exc:
                last_exception = exc
                if attempt < max_retries - 1:
                    logger.warning(
                        "Request error (attempt %d/%d): %s", attempt + 1, max_retries, exc
                    )
                    continue
                raise

        if last_exception:
            raise last_exception

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()
        self.authenticated = False

    async def __aenter__(self):
        await self.authenticate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
