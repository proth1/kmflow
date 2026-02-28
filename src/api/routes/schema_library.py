"""Schema intelligence library routes (Story #335).

Provides endpoints for querying pre-built schema templates
and checking platform support.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.models import User
from src.core.permissions import require_permission
from src.integrations.schema_library.loader import SchemaLibrary

router = APIRouter(prefix="/api/v1/schema-library", tags=["schema-library"])

# Singleton library instance (loaded once on first import)
_library = SchemaLibrary()


@router.get("/platforms")
async def list_platforms(
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List all supported platforms in the schema library."""
    platforms = _library.list_platforms()
    return {
        "platforms": platforms,
        "count": len(platforms),
    }


@router.get("/platforms/{platform}")
async def get_platform_template(
    platform: str,
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get the schema template for a specific platform.

    Returns 404 if the platform is not in the library,
    indicating manual mapping mode should be activated.
    """
    template = _library.get_template(platform)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No schema template found for platform '{platform}'. Use manual mapping mode.",
        )
    return template.to_dict()


@router.get("/platforms/{platform}/tables/{table_name}")
async def get_table_template(
    platform: str,
    table_name: str,
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get the schema template for a specific table within a platform."""
    template = _library.get_template(platform)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No schema template found for platform '{platform}'",
        )

    table = template.get_table(table_name)
    if table is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No table template '{table_name}' found for platform '{platform}'",
        )
    return table.to_dict()


@router.get("/platforms/{platform}/check")
async def check_platform_support(
    platform: str,
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Check if a platform has a pre-built schema template.

    Returns supported=false for platforms requiring manual mapping.
    """
    supported = _library.has_template(platform)
    return {
        "platform": platform,
        "supported": supported,
        "mode": "auto" if supported else "manual",
    }
