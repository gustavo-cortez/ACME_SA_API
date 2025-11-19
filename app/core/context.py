from __future__ import annotations

from .config import get_settings
from ..db.database import Database
from ..services.inventory import InventoryState
from .replication import ReplicaSynchronizer

settings = get_settings()
database = Database(settings.db_path())
inventory_state = InventoryState(settings.node_name, database)
synchronizer = ReplicaSynchronizer(settings)
