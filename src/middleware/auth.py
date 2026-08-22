"""Authentication middleware for Cisco ISE ERS API requests."""

import logging
from typing import Any, Callable, Dict, Optional

from src.core.api_registry import APIRegistry
from src.services.credential_manager import CredentialManager
from src.services.ise_api import ISEAPIClient

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """Middleware for handling authentication to an ISE deployment."""

    def __init__(self, cluster_name: str = "default"):
        """Initialize authentication middleware.

        Args:
            cluster_name: Name of the ISE deployment entry to authenticate with
        """
        self.cluster_name = cluster_name
        self.credential_manager = CredentialManager()
        self.api_client: Optional[ISEAPIClient] = None

    async def get_api_client(self) -> ISEAPIClient:
        """Get or create authenticated API client.

        Returns:
            Authenticated ISEAPIClient instance

        Raises:
            RuntimeError: If credentials not found or authentication fails
        """
        if self.api_client is not None:
            return self.api_client

        # Retrieve credentials from database
        credentials = None
        if self.cluster_name == "default":
            # If using default, try to get the first active ISE deployment
            credentials = await self.credential_manager.get_first_active_cluster_credentials()
            if credentials:
                self.cluster_name = credentials["name"]
                logger.info(f"Using first active ISE deployment: {self.cluster_name}")
        else:
            credentials = await self.credential_manager.get_credentials(self.cluster_name)

        if not credentials:
            raise RuntimeError(
                f"No credentials found for ISE deployment '{self.cluster_name}'. "
                f"Please configure an ISE deployment in the web UI first."
            )

        # Create and authenticate API client
        self.api_client = ISEAPIClient(
            base_url=credentials["url"],
            username=credentials["username"],
            password=credentials["password"],
            verify_ssl=credentials["verify_ssl"],
        )

        # Authenticate
        authenticated = await self.api_client.authenticate()
        if not authenticated:
            raise RuntimeError(
                f"Failed to authenticate with ISE deployment '{self.cluster_name}'"
            )

        logger.info(f"Successfully authenticated with ISE deployment '{self.cluster_name}'")
        return self.api_client

    async def execute_request(
        self,
        method: str,
        path: str,
        api_name: str = "ise",
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute authenticated API request.

        Args:
            method: HTTP method
            path: API endpoint path from the spec (e.g. ``/networkdevice/{id}``)
            api_name: Name of the API (``ise``)
            params: Query parameters
            json_data: JSON request body

        Returns:
            Response data as dictionary

        Raises:
            RuntimeError: If request fails
        """
        client = await self.get_api_client()

        # ERS spec paths are relative to the /ers/config root, so prepend the
        # API's base path unless it is already present. An API may legitimately
        # declare an empty base path — the API Service spec writes its paths
        # absolute from the server root — so None (unknown API) and "" (no
        # prefix wanted) must be distinguished rather than both treated as
        # falsy.
        base_path = APIRegistry.get_base_path_for_api(api_name)
        if base_path is None:
            base_path = "/ers/config"
        if base_path and not path.startswith(f"{base_path}/") and path != base_path:
            path = f"{base_path}{path}"

        try:
            response = await client.request(
                method=method,
                path=path,
                params=params,
                json_data=json_data,
            )

            # ERS answers a successful create with 201 and an empty body; the
            # new resource ID is only available from the Location header. A
            # delete or update returns 204 with no body at all.
            if response.status_code == 201:
                location = response.headers.get("location", "")
                return {
                    "status": "created",
                    "status_code": response.status_code,
                    "location": location,
                    "id": location.rstrip("/").rsplit("/", 1)[-1] if location else None,
                }

            if response.status_code == 204 or not response.content:
                return {"status": "success", "status_code": response.status_code}

            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()

            # Return text for non-JSON responses
            return {"data": response.text, "status_code": response.status_code}

        except Exception as e:
            logger.error(f"API request failed: {method} {path} - {e}")
            raise RuntimeError(f"API request failed: {e}")

    async def close(self):
        """Close API client connection."""
        if self.api_client:
            await self.api_client.close()
            self.api_client = None

    def __call__(self, func: Callable) -> Callable:
        """Decorator for adding authentication to functions.

        Args:
            func: Function to wrap with authentication

        Returns:
            Wrapped function with authentication
        """
        async def wrapper(*args, **kwargs):
            try:
                # Ensure we're authenticated before calling function
                await self.get_api_client()
                return await func(*args, **kwargs)
            finally:
                # Clean up if needed
                pass

        return wrapper
