from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    """Gerencia o arquivo SQLite de cada nó (schema e transações)."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.dsn = str(self.path)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;

                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    nome TEXT NOT NULL,
                    descricao TEXT,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clients (
                    id TEXT PRIMARY KEY,
                    nome TEXT NOT NULL,
                    documento TEXT,
                    email TEXT,
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    criado_em TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stock (
                    product_id TEXT PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
                    saldo INTEGER NOT NULL DEFAULT 0,
                    versao INTEGER NOT NULL DEFAULT 0,
                    atualizado_em TEXT NOT NULL,
                    origem TEXT NOT NULL,
                    referencia TEXT
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    cliente_id TEXT NOT NULL REFERENCES clients(id),
                    status TEXT NOT NULL,
                    criado_em TEXT NOT NULL,
                    origem TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    product_id TEXT NOT NULL REFERENCES products(id),
                    quantidade INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
                CREATE INDEX IF NOT EXISTS idx_orders_cliente ON orders(cliente_id);
                """
            )

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.dsn, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
