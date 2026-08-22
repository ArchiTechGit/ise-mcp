"""Main entry point for the Cisco ISE MCP Server."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings, init_db
from src.core.mcp_server import ISEMCP
from src.services.database_init import initialize_database_defaults


def parse_arguments():
    """Parse command-line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Cisco ISE MCP Server - Database-driven ISE deployment management"
    )
    parser.add_argument(
        "--deployment",
        "--cluster",
        type=str,
        dest="deployment",
        default="default",
        help="Name of the ISE deployment to connect to (must exist in database). Default: 'default'"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override logging level from environment"
    )

    return parser.parse_args()


def setup_logging(log_level: str = None):
    """Configure logging for the application.

    Args:
        log_level: Optional log level override
    """
    settings = get_settings()

    # Use provided log level or fall back to settings
    level = log_level or settings.log_level

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
        ],
    )

    # Set specific logger levels
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


async def main():
    """Main entry point."""
    # Parse command-line arguments
    args = parse_arguments()

    # Setup logging with optional override
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        logger.info("Starting Cisco ISE MCP Server...")

        # Initialize database
        logger.info("Initializing database...")
        await init_db()

        # Initialize default database values
        logger.info("Initializing database defaults...")
        await initialize_database_defaults()

        # Use ISE deployment name from command-line argument
        deployment_name = args.deployment
        logger.info(f"Using ISE deployment: {deployment_name}")

        # Create and run MCP server
        server = ISEMCP(deployment_name=deployment_name)

        logger.info(f"Connecting to ISE deployment: {deployment_name}")
        logger.info("Note: Edit mode is now controlled via database (security_config table)")

        await server.run()

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Server stopped")


if __name__ == "__main__":
    asyncio.run(main())
