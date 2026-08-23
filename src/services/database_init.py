"""Database initialization service for default data."""

import logging

from sqlalchemy import select, delete, text

from src.config.database import get_db
from src.core.api_loader import APILoader
from src.core.api_registry import APIRegistry
from src.core.tool_naming import (
    FAMILY_DISPLAY,
    RESOURCE_FAMILIES,
    build_tool_name_map,
    resources_for_families,
)
from src.models.security import SecurityConfig
from src.models.api_endpoint import APIEndpoint
from src.models.role import Role, RoleOperation

logger = logging.getLogger(__name__)


async def initialize_security_config():
    """Initialize default security configuration if none exists.

    This ensures that the security_config table has at least one row
    so the MCP server can read edit_mode settings from the database.
    """
    db = get_db()

    async with db.session() as session:
        # Check if any security config exists
        result = await session.execute(
            select(SecurityConfig).limit(1)
        )
        existing_config = result.scalar_one_or_none()

        if existing_config:
            logger.info("Security configuration already exists in database")
            logger.info(f"Edit mode: {existing_config.edit_mode_enabled}")
            return existing_config

        # Create default security configuration
        default_config = SecurityConfig(
            edit_mode_enabled=False,  # Start with read-only mode for safety
            audit_logging=True,       # Enable audit logging by default
            allowed_operations=[]     # No specific operation restrictions
        )

        session.add(default_config)
        await session.commit()
        await session.refresh(default_config)

        logger.info("Created default security configuration:")
        logger.info(f"  - Edit mode: {default_config.edit_mode_enabled}")
        logger.info(f"  - Audit logging: {default_config.audit_logging}")
        logger.info("  - Update via Web UI or database to enable write operations")

        return default_config


async def sync_api_endpoints():
    """Sync API endpoints from the OpenAPI specification to the database.

    Loads every operation from the ISE ERS spec and populates the
    api_endpoints table for RBAC operation selection. Each row also records
    the derived MCP tool name: the ERS spec declares no operationId, so both
    the operation ID and the tool name are synthesized by
    src/core/tool_naming.py and cannot be reconstructed in SQL.
    """
    db = get_db()

    api_loader = APILoader()
    total_loaded = 0
    total_updated = 0

    async with db.session() as session:
        for api_def in APIRegistry.get_enabled_apis():
            api_name = api_def.name
            spec = api_loader.load_openapi_spec(api_def.spec_file)

            if not spec:
                logger.warning("Skipping %s: spec %s could not be loaded", api_name, api_def.spec_file)
                continue

            try:
                operations = api_loader.list_operations(spec)
                tool_names = build_tool_name_map(
                    [op["operation_id"] for op in operations], api_def.tool_prefix
                )

                operations_added = 0
                operations_updated = 0

                for op in operations:
                    operation_id = op["operation_id"]
                    method = op["method"]
                    tool_name = tool_names[operation_id]
                    description = op.get("description") or op.get("summary") or ""

                    existing = await session.execute(
                        select(APIEndpoint).where(
                            APIEndpoint.api_name == api_name,
                            APIEndpoint.operation_id == operation_id,
                        )
                    )
                    endpoint = existing.scalar_one_or_none()

                    if endpoint:
                        # Backfill the tool name for rows synced before it existed
                        if endpoint.tool_name != tool_name:
                            endpoint.tool_name = tool_name
                            operations_updated += 1
                        continue

                    endpoint = APIEndpoint(
                        api_name=api_name,
                        operation_id=operation_id,
                        tool_name=tool_name,
                        http_method=method,
                        path=op["path"],
                        enabled=True,
                        requires_edit_mode=method in ("POST", "PUT", "DELETE", "PATCH"),
                        description=description[:500] if description else None,
                    )
                    session.add(endpoint)
                    operations_added += 1

                await session.commit()
                logger.info(
                    "Loaded %d new operations (%d tool names backfilled) from %s API",
                    operations_added, operations_updated, api_name,
                )
                total_loaded += operations_added
                total_updated += operations_updated

            except Exception as e:
                await session.rollback()
                logger.error("Error syncing OpenAPI spec %s: %s", api_def.spec_file, e)

    logger.info(
        "Total API endpoints synced to database: %d new, %d updated",
        total_loaded, total_updated,
    )


async def sync_role_operations():
    """Sync default role operations for system roles.

    This ensures that system roles (Administrator, Operator, Viewer) have
    appropriate operations assigned after api_endpoints are loaded.
    """
    db = get_db()

    async with db.session() as session:
        # Get system roles
        result = await session.execute(
            select(Role).where(Role.is_system_role == True)
        )
        system_roles = {role.name: role.id for role in result.scalars().all()}

        if not system_roles:
            logger.warning("No system roles found - skipping role operations sync")
            return

        # Check if Administrator role has any operations
        admin_role_id = system_roles.get("Administrator")
        if admin_role_id:
            existing = await session.execute(
                select(RoleOperation).where(RoleOperation.role_id == admin_role_id).limit(1)
            )
            if existing.scalar_one_or_none():
                logger.info("Role operations already populated - skipping sync")
                return

        # Populate operations for each system role
        for role_name, role_id in system_roles.items():
            # role_operations stores the MCP tool name, which is synthesized
            # from the spec rather than concatenated (see tool_naming.py).
            if role_name == "Administrator":
                # Admin gets all operations
                await session.execute(text("""
                    INSERT INTO role_operations (role_id, operation_name, created_at)
                    SELECT :role_id, tool_name, NOW()
                    FROM api_endpoints
                    WHERE tool_name IS NOT NULL
                    ON CONFLICT (role_id, operation_name) DO NOTHING
                """), {"role_id": role_id})
                logger.info(f"Assigned all operations to Administrator role")

            elif role_name in ("Operator", "Network Operator"):
                # Operator gets GET operations only. Both names are matched
                # because schema.sql seeds "Operator" while migration 002 seeds
                # "Network Operator"; matching only one leaves the other role
                # with no operations at all.
                await session.execute(text("""
                    INSERT INTO role_operations (role_id, operation_name, created_at)
                    SELECT :role_id, tool_name, NOW()
                    FROM api_endpoints
                    WHERE tool_name IS NOT NULL
                      AND http_method = 'GET'
                    ON CONFLICT (role_id, operation_name) DO NOTHING
                """), {"role_id": role_id})
                logger.info(f"Assigned GET operations to Operator role")

            elif role_name in ("Viewer", "Read-Only User"):
                # Viewer gets read operations only. ERS operation IDs end in
                # the action, e.g. "networkdevice_getAll" / "sgt_getById".
                await session.execute(text("""
                    INSERT INTO role_operations (role_id, operation_name, created_at)
                    SELECT :role_id, tool_name, NOW()
                    FROM api_endpoints
                    WHERE tool_name IS NOT NULL
                      AND http_method = 'GET'
                      AND (operation_id LIKE '%\\_get%' OR operation_id LIKE '%\\_fetch%')
                    ON CONFLICT (role_id, operation_name) DO NOTHING
                """), {"role_id": role_id})
                logger.info(f"Assigned list/get operations to Viewer role")

        await session.commit()
        logger.info("Role operations sync completed")


async def sync_tool_profile_operations():
    """Create and populate one tool profile per API category.

    MCP clients surface far fewer tools than the 1,007 this server advertises, so
    a profile per category is how an operator scopes a user to a workable set.
    Profiles are derived from the registry rather than written out in SQL, so
    registering a new spec produces its profile automatically:

      * one per registered API — "Open API - Policy", "Monitoring - Live
        Sessions", and so on
      * one per ERS resource family, because ERS alone is 395 operations and a
        single profile for it would not narrow anything
      * the pre-seeded cross-cutting profiles (all-reads, network operator,
        infrastructure viewer) are populated as before

    "Full Access" is deliberately left empty: ``max_tools == 0`` with no
    operations is the sentinel that means *no filtering*, and it is what the
    Administrator role points at. Every profile created here is therefore given
    a non-zero ``max_tools`` equal to its own size, so a profile that somehow
    ended up empty could never be mistaken for Full Access and silently grant
    everything.

    A profile that already has operations is left alone, so edits made in the
    web UI are never overwritten.
    """
    db = get_db()

    async with db.session() as session:

        async def upsert_profile(name: str, description: str, tool_names: list) -> None:
            """Create the profile if absent, then populate it if it is empty."""
            if not tool_names:
                logger.warning(
                    "Skipping tool profile '%s': no operations resolved for it", name
                )
                return

            await session.execute(
                text(
                    "INSERT INTO tool_profiles "
                    "(name, description, max_tools, is_active, created_at, updated_at) "
                    "VALUES (:name, :descr, :cap, TRUE, NOW(), NOW()) "
                    "ON CONFLICT (name) DO NOTHING"
                ),
                {"name": name, "descr": description[:500], "cap": len(tool_names)},
            )

            row = await session.execute(
                text("SELECT id FROM tool_profiles WHERE name = :name"), {"name": name}
            )
            profile_id = row.scalar_one_or_none()
            if profile_id is None:
                return

            existing = await session.execute(
                text("SELECT 1 FROM tool_profile_operations WHERE profile_id = :pid LIMIT 1"),
                {"pid": profile_id},
            )
            if existing.scalar_one_or_none():
                return

            await session.execute(
                text(
                    "INSERT INTO tool_profile_operations "
                    "(profile_id, operation_name, created_at) "
                    "SELECT :pid, unnest(CAST(:names AS text[])), NOW() "
                    "ON CONFLICT DO NOTHING"
                ),
                {"pid": profile_id, "names": tool_names},
            )
            logger.info(
                "Tool profile '%s': %d operations", name, len(tool_names)
            )

        # ---- one profile per registered API ----
        for api_def in APIRegistry.get_enabled_apis():
            rows = await session.execute(
                text(
                    "SELECT tool_name FROM api_endpoints "
                    "WHERE api_name = :api AND tool_name IS NOT NULL ORDER BY tool_name"
                ),
                {"api": api_def.name},
            )
            names = [r[0] for r in rows.all()]

            # ERS is split by resource family below instead of one 395-tool profile.
            if api_def.name == "ise":
                continue

            label = api_def.display_name.replace("Cisco ISE Open API — ", "Open API - ")
            label = label.replace("Cisco ISE Monitoring (MnT)", "Monitoring - Live Sessions")
            label = label.replace(
                "Cisco ISE API Service (Open API enablement)", "Open API Enablement"
            )
            await upsert_profile(label, api_def.description, names)

        # ---- one profile per ERS resource family ----
        for family in RESOURCE_FAMILIES:
            resources = sorted(resources_for_families(family))
            rows = await session.execute(
                text(
                    "SELECT tool_name FROM api_endpoints "
                    "WHERE api_name = 'ise' AND tool_name IS NOT NULL "
                    "  AND split_part(operation_id, '_', 1) = ANY(:resources) "
                    "ORDER BY tool_name"
                ),
                {"resources": resources},
            )
            names = [r[0] for r in rows.all()]
            await upsert_profile(
                f"ERS - {FAMILY_DISPLAY.get(family, family.title())}",
                f"ISE ERS operations for the {family} resource family",
                names,
            )

        # ---- pre-seeded cross-cutting profiles ----
        # (profile name, resource families or None for every API, read-only?)
        cross_cutting = [
            ("Read-Only Analyst", None, True),
            ("Network Operator", ("network", "policy"), False),
            ("Infrastructure Viewer", ("deployment",), True),
        ]
        for profile_name, families, read_only in cross_cutting:
            row = await session.execute(
                text("SELECT id FROM tool_profiles WHERE name = :name"),
                {"name": profile_name},
            )
            profile_id = row.scalar_one_or_none()
            if profile_id is None:
                continue

            existing = await session.execute(
                text("SELECT 1 FROM tool_profile_operations WHERE profile_id = :pid LIMIT 1"),
                {"pid": profile_id},
            )
            if existing.scalar_one_or_none():
                continue

            conditions = ["tool_name IS NOT NULL"]
            params = {"pid": profile_id}
            if read_only:
                conditions.append("http_method = 'GET'")
            if families is not None:
                # ERS operation IDs are "{resource}_{action}".
                conditions.append(
                    "api_name = 'ise' AND split_part(operation_id, '_', 1) = ANY(:resources)"
                )
                params["resources"] = sorted(resources_for_families(*families))

            await session.execute(
                text(
                    "INSERT INTO tool_profile_operations (profile_id, operation_name, created_at) "
                    "SELECT :pid, tool_name, NOW() FROM api_endpoints "
                    f"WHERE {' AND '.join(conditions)} "
                    "ON CONFLICT DO NOTHING"
                ),
                params,
            )
            count = await session.execute(
                text("SELECT count(*) FROM tool_profile_operations WHERE profile_id = :pid"),
                {"pid": profile_id},
            )
            logger.info(
                "Tool profile '%s': %d operations", profile_name, count.scalar() or 0
            )

        await session.commit()
        logger.info("Tool profile sync completed")


async def initialize_database_defaults():
    """Initialize all default database records.

    This function is called during database initialization to ensure
    required default data exists.
    """
    logger.info("Initializing database default values...")

    # Initialize security configuration
    await initialize_security_config()

    # Sync API endpoints from OpenAPI specs
    await sync_api_endpoints()

    # Sync role operations for system roles
    await sync_role_operations()

    # Populate the family-scoped default tool profiles
    await sync_tool_profile_operations()

    logger.info("Database initialization completed")
