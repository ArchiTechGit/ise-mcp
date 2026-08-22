"""Configuration settings for the Cisco ISE MCP Server."""

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Database Configuration
    database_url: str = Field(
        default="postgresql://mcp_user:changeme@localhost:5432/ise_mcp",
        description="PostgreSQL database connection URL"
    )

    # Cisco ISE Configuration
    ise_host_url: str = Field(
        default="https://192.168.70.101:9060",
        description=(
            "ISE Primary PAN base URL, including the ERS port "
            "(ERS listens on 9060, not 443)"
        )
    )
    ise_username: str = Field(
        default="ersadmin",
        description="ERS admin username (must belong to an ERS Admin or ERS Operator group)"
    )
    ise_password: str = Field(
        default="",
        description="ERS admin password"
    )
    ise_verify_ssl: bool = Field(
        default=False,
        description="Verify SSL certificates for ISE connections"
    )
    ise_cts_port: int = Field(
        default=9063,
        description=(
            "Port serving the TrustSec (CTS) subset of the ERS API. Requests to "
            "/ctsapi/ paths are re-pointed here; set to 0 to disable when ISE is "
            "behind a proxy that serves both on one port."
        )
    )
    ise_admin_port: int = Field(
        default=443,
        description=(
            "Port of the ISE API gateway, which serves the Open API "
            "(/api/v1/...) and the admin family (/admin/API/..., covering the "
            "API Service and the Monitoring API). Requests to those paths are "
            "re-pointed here; set to 0 to disable."
        )
    )

    # Security Configuration
    edit_mode_enabled: bool = Field(
        default=False,
        description="Enable write operations (POST/PUT/DELETE)"
    )
    encryption_key: Optional[str] = Field(
        default=None,
        description="Fernet encryption key for credential storage"
    )
    session_secret_key: str = Field(
        default="change-me-in-production",
        description="Secret key for session management"
    )
    session_timeout_minutes: int = Field(
        default=30,
        description="Session timeout in minutes"
    )

    # Server Configuration
    mcp_server_host: str = Field(
        default="0.0.0.0",
        description="MCP server bind host"
    )
    mcp_server_port: int = Field(
        default=8080,
        description="MCP server port"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )

    # API Configuration
    api_timeout: int = Field(
        default=30,
        description="ISE API request timeout in seconds"
    )
    api_retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts for failed API requests"
    )

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return os.getenv("ENVIRONMENT", "development").lower() == "production"

    def get_encryption_key(self) -> bytes:
        """Get or generate encryption key for credential storage."""
        if self.encryption_key:
            return self.encryption_key.encode()

        # Generate a new key if not provided (dev only)
        if not self.is_production:
            from cryptography.fernet import Fernet
            return Fernet.generate_key()

        raise ValueError(
            "ENCRYPTION_KEY must be set in production. "
            "Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
