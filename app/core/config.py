from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


def _split_csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    node_name: str = field(default_factory=lambda: os.getenv("NODE_NAME", "node-a"))
    peers: List[str] = field(default_factory=lambda: _split_csv(os.getenv("PEERS")))
    replication_token: str = field(
        default_factory=lambda: os.getenv("REPLICATION_TOKEN", "replica-secret")
    )
    replication_retry_seconds: int = field(
        default_factory=lambda: int(os.getenv("REPLICATION_RETRY_SECONDS", "10"))
    )
    database_dir: str = field(default_factory=lambda: os.getenv("DATABASE_DIR", "data"))
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", "acme-jwt-secret"))
    jwt_expires_minutes: int = field(
        default_factory=lambda: int(os.getenv("JWT_EXPIRES_MINUTES", "60"))
    )
    admin_user: str = field(default_factory=lambda: os.getenv("ADMIN_USER", "admin"))
    admin_password: str = field(
        default_factory=lambda: os.getenv("ADMIN_PASSWORD", "admin123")
    )

    def db_path(self) -> Path:
        base = Path(self.database_dir)
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{self.node_name}.db"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
