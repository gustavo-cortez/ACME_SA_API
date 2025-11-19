from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.context import inventory_state, settings, synchronizer
from ..core.dependencies import get_current_user

router = APIRouter(tags=["Monitoramento"])


@router.get("/status")
async def status_endpoint(user=Depends(get_current_user)):
    return {
        "node": settings.node_name,
        "database": str(settings.db_path()),
        "snapshot": inventory_state.snapshot(),
        "replicacao": synchronizer.status(),
    }
