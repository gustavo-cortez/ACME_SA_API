from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Sequence

from ..db.database import Database


class StockUnavailableError(Exception):
    """Lançada quando não há saldo para concluir uma operação."""


class EntityNotFound(Exception):
    """Entidade obrigatória não localizada no banco."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ClientRecord:
    id: str
    nome: str
    documento: str | None
    email: str | None
    criado_em: str
    atualizado_em: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ProductRecord:
    id: str
    nome: str
    descricao: str | None
    ativo: bool
    criado_em: str
    atualizado_em: str

    def to_dict(self) -> Dict:
        data = asdict(self)
        data["ativo"] = bool(self.ativo)
        return data


@dataclass
class UserRecord:
    username: str
    role: str
    criado_em: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class OrderItem:
    produto_id: str
    quantidade: int
    produto_nome: str | None = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class OrderRecord:
    id: str
    cliente_id: str
    cliente_nome: str
    itens: List[OrderItem]
    status: str
    criado_em: str
    origem: str

    def to_dict(self) -> Dict:
        data = asdict(self)
        data["itens"] = [item.to_dict() for item in self.itens]
        return data


@dataclass
class StockEntry:
    product_id: str
    saldo: int = 0
    versao: int = 0
    atualizado_em: str = field(default_factory=_utcnow)
    origem: str = ""
    referencia: str | None = None

    def to_dict(self) -> Dict:
        return asdict(self)


class InventoryState:
    """Coordena bloqueios e persistência das entidades do domínio ACME/SA."""

    def __init__(self, node_name: str, database: Database):
        self.node_name = node_name
        self.db = database
        self._locks: Dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Helpers internos
    def _get_lock(self, product_id: str) -> asyncio.Lock:
        lock = self._locks.get(product_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[product_id] = lock
        return lock

    async def _acquire_product_locks(self, produtos: Iterable[str]) -> List[asyncio.Lock]:
        locks: List[asyncio.Lock] = []
        for produto in sorted(set(produtos)):
            lock = self._get_lock(produto)
            await lock.acquire()
            locks.append(lock)
        return locks

    @staticmethod
    def _release_locks(locks: Sequence[asyncio.Lock]) -> None:
        for lock in reversed(locks):
            if lock.locked():
                lock.release()

    # ------------------------------------------------------------------
    # Conversões de linha para registros
    @staticmethod
    def _row_to_client(row) -> ClientRecord:
        return ClientRecord(
            id=row["id"],
            nome=row["nome"],
            documento=row["documento"],
            email=row["email"],
            criado_em=row["criado_em"],
            atualizado_em=row["atualizado_em"],
        )

    @staticmethod
    def _row_to_product(row) -> ProductRecord:
        return ProductRecord(
            id=row["id"],
            nome=row["nome"],
            descricao=row["descricao"],
            ativo=bool(row["ativo"]),
            criado_em=row["criado_em"],
            atualizado_em=row["atualizado_em"],
        )

    @staticmethod
    def _row_to_stock(row) -> StockEntry:
        return StockEntry(
            product_id=row["product_id"],
            saldo=row["saldo"],
            versao=row["versao"],
            atualizado_em=row["atualizado_em"],
            origem=row["origem"],
            referencia=row["referencia"],
        )

    @staticmethod
    def _row_to_user(row) -> UserRecord:
        return UserRecord(username=row["username"], role=row["role"], criado_em=row["criado_em"])

    # ------------------------------------------------------------------
    # Clientes
    def upsert_client(
        self, *, client_id: str, nome: str, documento: str | None, email: str | None
    ) -> ClientRecord:
        agora = _utcnow()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO clients (id, nome, documento, email, criado_em, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    nome=excluded.nome,
                    documento=excluded.documento,
                    email=excluded.email,
                    atualizado_em=excluded.atualizado_em
                """,
                (client_id, nome, documento, email, agora, agora),
            )
            row = conn.execute(
                "SELECT id, nome, documento, email, criado_em, atualizado_em FROM clients WHERE id = ?",
                (client_id,),
            ).fetchone()
        return self._row_to_client(row)

    def get_client(self, client_id: str) -> ClientRecord | None:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT id, nome, documento, email, criado_em, atualizado_em FROM clients WHERE id = ?",
                (client_id,),
            ).fetchone()
        return self._row_to_client(row) if row else None

    def list_clients(self) -> List[ClientRecord]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT id, nome, documento, email, criado_em, atualizado_em FROM clients ORDER BY nome"
            ).fetchall()
        return [self._row_to_client(row) for row in rows]

    def apply_remote_client(self, payload: Dict) -> ClientRecord:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO clients (id, nome, documento, email, criado_em, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    nome=excluded.nome,
                    documento=excluded.documento,
                    email=excluded.email,
                    atualizado_em=excluded.atualizado_em
                """,
                (
                    payload["id"],
                    payload.get("nome", ""),
                    payload.get("documento"),
                    payload.get("email"),
                    payload.get("criado_em", _utcnow()),
                    payload.get("atualizado_em", _utcnow()),
                ),
            )
            row = conn.execute(
                "SELECT id, nome, documento, email, criado_em, atualizado_em FROM clients WHERE id = ?",
                (payload["id"],),
            ).fetchone()
        return self._row_to_client(row)

    # ------------------------------------------------------------------
    # Produtos
    def upsert_product(
        self,
        *,
        product_id: str,
        nome: str,
        descricao: str | None,
        ativo: bool = True,
    ) -> ProductRecord:
        agora = _utcnow()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO products (id, nome, descricao, ativo, criado_em, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    nome=excluded.nome,
                    descricao=excluded.descricao,
                    ativo=excluded.ativo,
                    atualizado_em=excluded.atualizado_em
                """,
                (product_id, nome, descricao, int(ativo), agora, agora),
            )
            row = conn.execute(
                "SELECT id, nome, descricao, ativo, criado_em, atualizado_em FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
        return self._row_to_product(row)

    def get_product(self, product_id: str) -> ProductRecord | None:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT id, nome, descricao, ativo, criado_em, atualizado_em FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
        return self._row_to_product(row) if row else None

    def list_products(self) -> List[ProductRecord]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT id, nome, descricao, ativo, criado_em, atualizado_em FROM products ORDER BY nome"
            ).fetchall()
        return [self._row_to_product(row) for row in rows]

    def apply_remote_product(self, payload: Dict) -> ProductRecord:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO products (id, nome, descricao, ativo, criado_em, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    nome=excluded.nome,
                    descricao=excluded.descricao,
                    ativo=excluded.ativo,
                    atualizado_em=excluded.atualizado_em
                """,
                (
                    payload["id"],
                    payload.get("nome", ""),
                    payload.get("descricao"),
                    int(payload.get("ativo", True)),
                    payload.get("criado_em", _utcnow()),
                    payload.get("atualizado_em", _utcnow()),
                ),
            )
            row = conn.execute(
                "SELECT id, nome, descricao, ativo, criado_em, atualizado_em FROM products WHERE id = ?",
                (payload["id"],),
            ).fetchone()
        return self._row_to_product(row)

    # ------------------------------------------------------------------
    # Usuários
    def get_user(self, username: str) -> tuple[UserRecord, str] | None:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT username, password_hash, role, criado_em FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_user(row), row["password_hash"]

    def upsert_user(
        self, *, username: str, password_hash: str, role: str, criado_em: str | None = None
    ) -> UserRecord:
        agora = _utcnow()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, criado_em)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password_hash=excluded.password_hash,
                    role=excluded.role
                """,
                (username, password_hash, role, criado_em or agora),
            )
            row = conn.execute(
                "SELECT username, role, criado_em FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return self._row_to_user(row)

    def apply_remote_user(self, payload: Dict) -> UserRecord:
        return self.upsert_user(
            username=payload["username"],
            password_hash=payload["password_hash"],
            role=payload.get("role", "user"),
            criado_em=payload.get("criado_em"),
        )

    # ------------------------------------------------------------------
    # Estoque / pedidos
    def _fetch_client_or_fail(self, conn, cliente_id: str) -> ClientRecord:
        row = conn.execute(
            "SELECT id, nome, documento, email, criado_em, atualizado_em FROM clients WHERE id = ?",
            (cliente_id,),
        ).fetchone()
        if not row:
            raise EntityNotFound(f"Cliente {cliente_id} inexistente")
        return self._row_to_client(row)

    def _fetch_product_or_fail(self, conn, product_id: str) -> ProductRecord:
        row = conn.execute(
            "SELECT id, nome, descricao, ativo, criado_em, atualizado_em FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
        if not row:
            raise EntityNotFound(f"Produto {product_id} inexistente")
        product = self._row_to_product(row)
        if not product.ativo:
            raise ValueError(f"Produto {product_id} está inativo")
        return product

    def _fetch_stock(self, conn, product_id: str) -> StockEntry:
        row = conn.execute(
            "SELECT product_id, saldo, versao, atualizado_em, origem, referencia FROM stock WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        if row:
            return self._row_to_stock(row)
        agora = _utcnow()
        conn.execute(
            "INSERT INTO stock (product_id, saldo, versao, atualizado_em, origem, referencia) VALUES (?, 0, 0, ?, ?, NULL)",
            (product_id, agora, "bootstrap"),
        )
        return StockEntry(product_id=product_id, saldo=0, versao=0, atualizado_em=agora, origem="bootstrap")

    async def adjust_stock(self, product_id: str, delta: int, referencia: str) -> StockEntry:
        locks = await self._acquire_product_locks([product_id])
        try:
            with self.db.transaction() as conn:
                self._fetch_product_or_fail(conn, product_id)
                entry = self._fetch_stock(conn, product_id)
                novo_saldo = entry.saldo + delta
                if novo_saldo < 0:
                    raise StockUnavailableError(f"Saldo insuficiente para {product_id}")
                versao = entry.versao + 1
                agora = _utcnow()
                conn.execute(
                    """
                    INSERT INTO stock (product_id, saldo, versao, atualizado_em, origem, referencia)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(product_id) DO UPDATE SET
                        saldo=excluded.saldo,
                        versao=excluded.versao,
                        atualizado_em=excluded.atualizado_em,
                        origem=excluded.origem,
                        referencia=excluded.referencia
                    """,
                    (product_id, novo_saldo, versao, agora, self.node_name, referencia),
                )
                return StockEntry(
                    product_id=product_id,
                    saldo=novo_saldo,
                    versao=versao,
                    atualizado_em=agora,
                    origem=self.node_name,
                    referencia=referencia,
                )
        finally:
            self._release_locks(locks)

    async def register_order(
        self,
        cliente_id: str,
        itens: Sequence[OrderItem],
        pedido_id: str | None = None,
    ) -> tuple[OrderRecord, List[StockEntry], Dict[str, ProductRecord]]:
        if not itens:
            raise ValueError("Pedido precisa de itens")
        pedido = pedido_id or str(uuid.uuid4())
        produtos = [item.produto_id for item in itens]
        locks = await self._acquire_product_locks(produtos)
        try:
            with self.db.transaction() as conn:
                cliente = self._fetch_client_or_fail(conn, cliente_id)
                produtos_cache: Dict[str, ProductRecord] = {}
                for item in itens:
                    produto = self._fetch_product_or_fail(conn, item.produto_id)
                    produtos_cache[item.produto_id] = produto
                    entry = self._fetch_stock(conn, item.produto_id)
                    if entry.saldo < item.quantidade:
                        raise StockUnavailableError(
                            f"Produto {item.produto_id} sem saldo suficiente"
                        )
                updated_entries: List[StockEntry] = []
                for item in itens:
                    entry = self._fetch_stock(conn, item.produto_id)
                    novo_saldo = entry.saldo - item.quantidade
                    versao = entry.versao + 1
                    agora = _utcnow()
                    referencia_texto = f"pedido:{pedido}"
                    conn.execute(
                        """
                        INSERT INTO stock (product_id, saldo, versao, atualizado_em, origem, referencia)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(product_id) DO UPDATE SET
                            saldo=excluded.saldo,
                            versao=excluded.versao,
                            atualizado_em=excluded.atualizado_em,
                            origem=excluded.origem,
                            referencia=excluded.referencia
                        """,
                        (item.produto_id, novo_saldo, versao, agora, self.node_name, referencia_texto),
                    )
                    updated_entries.append(
                        StockEntry(
                            product_id=item.produto_id,
                            saldo=novo_saldo,
                            versao=versao,
                            atualizado_em=agora,
                            origem=self.node_name,
                            referencia=referencia_texto,
                        )
                    )
                criado_em = _utcnow()
                conn.execute(
                    """
                    INSERT INTO orders (id, cliente_id, status, criado_em, origem)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        cliente_id=excluded.cliente_id,
                        status=excluded.status,
                        criado_em=excluded.criado_em,
                        origem=excluded.origem
                    """,
                    (pedido, cliente.id, "confirmado", criado_em, self.node_name),
                )
                conn.execute("DELETE FROM order_items WHERE order_id = ?", (pedido,))
                conn.executemany(
                    "INSERT INTO order_items (order_id, product_id, quantidade) VALUES (?, ?, ?)",
                    [(pedido, item.produto_id, item.quantidade) for item in itens],
                )
            order_items = [
                OrderItem(produto_id=item.produto_id, quantidade=item.quantidade, produto_nome=produtos_cache[item.produto_id].nome)
                for item in itens
            ]
            order = OrderRecord(
                id=pedido,
                cliente_id=cliente.id,
                cliente_nome=cliente.nome,
                itens=order_items,
                status="confirmado",
                criado_em=criado_em,
                origem=self.node_name,
            )
            return order, updated_entries, produtos_cache
        finally:
            self._release_locks(locks)

    async def apply_remote_stock(
        self,
        product_id: str,
        saldo: int,
        versao: int,
        origem: str,
        referencia: str | None,
        atualizado_em: str | None,
    ) -> StockEntry:
        locks = await self._acquire_product_locks([product_id])
        try:
            with self.db.transaction() as conn:
                self._fetch_product_or_fail(conn, product_id)
                local_entry = self._fetch_stock(conn, product_id)
                is_newer = versao > local_entry.versao or (
                    versao == local_entry.versao
                    and atualizado_em
                    and atualizado_em > local_entry.atualizado_em
                )
                if is_newer:
                    timestamp = atualizado_em or _utcnow()
                    conn.execute(
                        """
                        INSERT INTO stock (product_id, saldo, versao, atualizado_em, origem, referencia)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(product_id) DO UPDATE SET
                            saldo=excluded.saldo,
                            versao=excluded.versao,
                            atualizado_em=excluded.atualizado_em,
                            origem=excluded.origem,
                            referencia=excluded.referencia
                        """,
                        (product_id, saldo, versao, timestamp, origem, referencia),
                    )
                    return StockEntry(
                        product_id=product_id,
                        saldo=saldo,
                        versao=versao,
                        atualizado_em=timestamp,
                        origem=origem,
                        referencia=referencia,
                    )
                return local_entry
        finally:
            self._release_locks(locks)

    def apply_remote_order(
        self, payload: Dict, cliente: Dict | None, produtos: List[Dict]
    ) -> OrderRecord:
        if cliente:
            self.apply_remote_client(cliente)
        for produto in produtos:
            self.apply_remote_product(produto)
        itens_payload = payload.get("itens", [])
        with self.db.transaction() as conn:

            conn.execute(
                """
                INSERT INTO orders (id, cliente_id, status, criado_em, origem)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    cliente_id=excluded.cliente_id,
                    status=excluded.status,
                    criado_em=excluded.criado_em,
                    origem=excluded.origem
                """,
                (
                    payload["id"],
                    payload.get("cliente_id"),
                    payload.get("status", "confirmado"),
                    payload.get("criado_em", _utcnow()),
                    payload.get("origem", "replica"),
                ),
            )
            conn.execute("DELETE FROM order_items WHERE order_id = ?", (payload["id"],))
            conn.executemany(
                "INSERT INTO order_items (order_id, product_id, quantidade) VALUES (?, ?, ?)",
                [
                    (payload["id"], item["produto_id"], item["quantidade"])
                    for item in itens_payload
                ],
            )
        produtos_map = {produto["id"]: produto for produto in produtos}
        itens = [
            OrderItem(
                produto_id=item["produto_id"],
                quantidade=item["quantidade"],
                produto_nome=produtos_map.get(item["produto_id"], {}).get("nome"),
            )
            for item in itens_payload
        ]
        return OrderRecord(
            id=payload["id"],
            cliente_id=payload.get("cliente_id", ""),
            cliente_nome=(cliente or {}).get("nome", ""),
            itens=itens,
            status=payload.get("status", "confirmado"),
            criado_em=payload.get("criado_em", _utcnow()),
            origem=payload.get("origem", "replica"),
        )

    def get_order(self, pedido_id: str) -> OrderRecord | None:
        with self.db.transaction() as conn:
            row = conn.execute(
                """
                SELECT o.id, o.cliente_id, o.status, o.criado_em, o.origem,
                       c.nome as cliente_nome
                FROM orders o
                JOIN clients c ON c.id = o.cliente_id
                WHERE o.id = ?
                """,
                (pedido_id,),
            ).fetchone()
            if not row:
                return None
            itens_rows = conn.execute(
                """
                SELECT oi.product_id, oi.quantidade, p.nome
                FROM order_items oi
                JOIN products p ON p.id = oi.product_id
                WHERE oi.order_id = ?
                """,
                (pedido_id,),
            ).fetchall()
        itens = [
            OrderItem(produto_id=r["product_id"], quantidade=r["quantidade"], produto_nome=r["nome"])
            for r in itens_rows
        ]
        return OrderRecord(
            id=row["id"],
            cliente_id=row["cliente_id"],
            cliente_nome=row["cliente_nome"],
            itens=itens,
            status=row["status"],
            criado_em=row["criado_em"],
            origem=row["origem"],
        )

    def get_stock(self, product_id: str) -> StockEntry:
        with self.db.transaction() as conn:
            self._fetch_product_or_fail(conn, product_id)
            return self._fetch_stock(conn, product_id)

    def snapshot(self) -> Dict:
        with self.db.transaction() as conn:
            total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            total_clients = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            stock_rows = conn.execute(
                "SELECT product_id, saldo, versao, atualizado_em, origem, referencia FROM stock"
            ).fetchall()
        return {
            "node": self.node_name,
            "orders": total_orders,
            "clients": total_clients,
            "products": total_products,
            "stock": {row["product_id"]: self._row_to_stock(row).to_dict() for row in stock_rows},
        }
