from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, List, Literal, Type

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .database import Database
from .schemas import (
    ClientRequest,
    EstoqueUpdateRequest,
    LoginRequest,
    PedidoItemRequest,
    PedidoRequest,
    ProductRequest,
    TokenResponse,
    UserCreateRequest,
)
from .security import (
    create_access_token,
    decode_access_token,
    hash_password,
    require_replication_token,
    verify_password,
)
from .state import (
    EntityNotFound,
    InventoryState,
    OrderItem,
    ProductRecord,
    StockUnavailableError,
    UserRecord,
)
from .sync import ReplicaSynchronizer

settings = get_settings()
database = Database(settings.db_path())
state = InventoryState(settings.node_name, database)
synchronizer = ReplicaSynchronizer(settings)
app = FastAPI(
    title="ACME/SA - Plataforma Distribuída",
    version="3.2.0",
    description="Controle profissional de pedidos, estoque, clientes e usuários com replicação entre filiais.",
)
bearer_scheme = HTTPBearer(auto_error=False)
AllowedRoles = Literal["admin", "operador", "auditor"]

# ---------------------------------------------------------------------------
# Helpers de segurança


def _build_user_context(credentials: HTTPAuthorizationCredentials | None) -> UserRecord:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente")
    payload = decode_access_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    stored = state.get_user(username)
    if not stored:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado")
    user_record, _ = stored
    return user_record


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> UserRecord:
    return _build_user_context(credentials)


def require_admin(user: UserRecord = Depends(get_current_user)) -> UserRecord:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operação restrita a administradores")
    return user


async def _ensure_admin_user() -> None:
    stored = state.get_user(settings.admin_user)
    if stored:
        return
    password_hash = hash_password(settings.admin_password)
    user = state.upsert_user(username=settings.admin_user, password_hash=password_hash, role="admin")
    await synchronizer.broadcast(
        "user_upsert",
        {"user": user.to_dict(), "password_hash": password_hash},
    )


def _authenticate(username: str, password: str) -> TokenResponse:
    stored = state.get_user(username)
    if not stored:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    user_record, password_hash = stored
    if not verify_password(password, password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    token = create_access_token(subject=user_record.username, role=user_record.role)
    return TokenResponse(access_token=token)


# ---------------------------------------------------------------------------
# Utilidades de parsing

def dual_request_body(model: Type) -> Dict[str, Any]:
    schema = model.model_json_schema()
    return {
        "requestBody": {
            "content": {
                "application/json": {"schema": schema},
                "application/x-www-form-urlencoded": {"schema": schema},
            }
        }
    }


async def parse_payload(request: Request, model: Type) -> Any:
    content_type = request.headers.get("content-type", "").lower()
    data: Dict[str, Any]
    if "application/json" in content_type:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)
    # Conversões específicas
    if model is PedidoRequest:
        itens_raw = data.get("itens") or data.get("itens_json")
        if isinstance(itens_raw, str):
            try:
                data["itens"] = json.loads(itens_raw)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Itens inválidos (JSON)") from exc
        elif itens_raw is None and "itens" not in data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Itens obrigatórios")
    return model(**data)


# ---------------------------------------------------------------------------
# Rotas organizadas por domínio

auth_router = APIRouter(prefix="/auth", tags=["Autenticação"])
users_router = APIRouter(prefix="/usuarios", tags=["Usuários"])
clients_router = APIRouter(prefix="/clientes", tags=["Clientes"])
products_router = APIRouter(prefix="/produtos", tags=["Produtos"])
orders_router = APIRouter(prefix="/pedido", tags=["Pedidos"])
inventory_router = APIRouter(prefix="/estoque", tags=["Estoque"])
status_router = APIRouter(tags=["Monitoramento"])
replica_router = APIRouter(prefix="/replica", tags=["Replicação"])


@auth_router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login via JSON ou x-www-form-urlencoded",
    openapi_extra=dual_request_body(LoginRequest),
)
async def login(request: Request):
    payload: LoginRequest = await parse_payload(request, LoginRequest)
    return _authenticate(payload.username, payload.password)


@users_router.post(
    "",
    dependencies=[Depends(require_admin)],
    openapi_extra=dual_request_body(UserCreateRequest),
)
async def criar_usuario(request: Request):
    payload: UserCreateRequest = await parse_payload(request, UserCreateRequest)
    password_hash = hash_password(payload.password)
    user = state.upsert_user(username=payload.username, password_hash=password_hash, role=payload.role)
    await synchronizer.broadcast(
        "user_upsert",
        {"user": user.to_dict(), "password_hash": password_hash},
    )
    return user.to_dict()


@users_router.get("/me")
async def usuario_atual(user: UserRecord = Depends(get_current_user)):
    return user.to_dict()


@clients_router.post(
    "",
    dependencies=[Depends(get_current_user)],
    openapi_extra=dual_request_body(ClientRequest),
)
async def criar_cliente(request: Request):
    payload: ClientRequest = await parse_payload(request, ClientRequest)
    client_id = str(uuid.uuid4())
    client = state.upsert_client(
        client_id=client_id,
        nome=payload.nome,
        documento=payload.documento,
        email=payload.email,
    )
    await synchronizer.broadcast("client_upsert", {"client": client.to_dict()})
    return client.to_dict()


@clients_router.get("")
async def listar_clientes(user: UserRecord = Depends(get_current_user)):
    return [client.to_dict() for client in state.list_clients()]


@clients_router.get("/{cliente_id}")
async def obter_cliente(cliente_id: str, user: UserRecord = Depends(get_current_user)):
    client = state.get_client(cliente_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
    return client.to_dict()


@products_router.post(
    "",
    dependencies=[Depends(require_admin)],
    openapi_extra=dual_request_body(ProductRequest),
)
async def criar_produto(request: Request):
    payload: ProductRequest = await parse_payload(request, ProductRequest)
    product_id = str(uuid.uuid4())
    product = state.upsert_product(
        product_id=product_id,
        nome=payload.nome,
        descricao=payload.descricao,
        ativo=payload.ativo,
    )
    await synchronizer.broadcast("product_upsert", {"product": product.to_dict()})
    return product.to_dict()


@products_router.get("")
async def listar_produtos(user: UserRecord = Depends(get_current_user)):
    return [product.to_dict() for product in state.list_products()]


@products_router.get("/{produto_id}")
async def obter_produto(produto_id: str, user: UserRecord = Depends(get_current_user)):
    product = state.get_product(produto_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado")
    return product.to_dict()


@orders_router.post(
    "",
    openapi_extra=dual_request_body(PedidoRequest),
)
async def criar_pedido(request: Request, user: UserRecord = Depends(get_current_user)):
    payload: PedidoRequest = await parse_payload(request, PedidoRequest)
    if not payload.cliente_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cliente_id é obrigatório")
    itens = [OrderItem(produto_id=item.produto_id, quantidade=item.quantidade) for item in payload.itens]
    try:
        order, stock_entries, produtos_map = await state.register_order(payload.cliente_id, itens, payload.pedido_id)
    except EntityNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StockUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    cliente = state.get_client(order.cliente_id)
    produtos_payload = [produtos_map[pid].to_dict() for pid in produtos_map]
    order_data = order.to_dict()
    await synchronizer.broadcast(
        "order_created",
        {
            "order": order_data,
            "cliente": cliente.to_dict() if cliente else None,
            "produtos": produtos_payload,
        },
    )
    await asyncio.gather(
        *[
            synchronizer.broadcast(
                "stock_update",
                {
                    "entry": entry.to_dict(),
                    "produto": produtos_map[entry.product_id].to_dict(),
                },
            )
            for entry in stock_entries
        ]
    )
    return {"pedido": order_data}


@orders_router.get("/{pedido_id}")
async def obter_pedido(pedido_id: str, user: UserRecord = Depends(get_current_user)):
    order = state.get_order(pedido_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado")
    return order.to_dict()


@inventory_router.get("/{produto_id}")
async def obter_estoque(produto_id: str, user: UserRecord = Depends(get_current_user)):
    entry = state.get_stock(produto_id)
    return entry.to_dict()


@inventory_router.put(
    "/{produto_id}",
    openapi_extra=dual_request_body(EstoqueUpdateRequest),
)
async def atualizar_estoque(request: Request, produto_id: str, user: UserRecord = Depends(get_current_user)):
    payload: EstoqueUpdateRequest = await parse_payload(request, EstoqueUpdateRequest)
    if payload.variacao == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Variação não pode ser zero")
    referencia = payload.motivo or "ajuste-manual"
    try:
        entry = await state.adjust_stock(produto_id, payload.variacao, referencia)
    except (StockUnavailableError, EntityNotFound) as exc:
        code = status.HTTP_404_NOT_FOUND if isinstance(exc, EntityNotFound) else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    product = state.get_product(produto_id)
    await synchronizer.broadcast(
        "stock_update",
        {"entry": entry.to_dict(), "produto": product.to_dict() if product else None},
    )
    return entry.to_dict()


@status_router.get("/status")
async def status_endpoint(user: UserRecord = Depends(get_current_user)):
    return {
        "node": settings.node_name,
        "database": str(settings.db_path()),
        "snapshot": state.snapshot(),
        "replicacao": synchronizer.status(),
    }


@replica_router.post("/event", dependencies=[Depends(require_replication_token)])
async def aplicar_evento(evento: Dict[str, Any]):
    tipo = evento.get("tipo")
    payload = evento.get("payload", {})
    if tipo == "order_created":
        order_payload = payload.get("order")
        cliente_payload = payload.get("cliente")
        produtos_payload = payload.get("produtos", [])
        if not order_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload inválido para pedido")
        record = state.apply_remote_order(order_payload, cliente_payload, produtos_payload)
        return {"status": "ok", "order": record.to_dict()}
    if tipo == "stock_update":
        entry_payload = payload.get("entry")
        produto_payload = payload.get("produto")
        if produto_payload:
            state.apply_remote_product(produto_payload)
        if not entry_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload inválido para estoque")
        entry = await state.apply_remote_stock(
            product_id=entry_payload["product_id"],
            saldo=entry_payload["saldo"],
            versao=entry_payload["versao"],
            origem=entry_payload.get("origem", "replica"),
            referencia=entry_payload.get("referencia"),
            atualizado_em=entry_payload.get("atualizado_em"),
        )
        return {"status": "ok", "entry": entry.to_dict()}
    if tipo == "client_upsert":
        client_payload = payload.get("client")
        if not client_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload inválido para cliente")
        client = state.apply_remote_client(client_payload)
        return {"status": "ok", "client": client.to_dict()}
    if tipo == "product_upsert":
        product_payload = payload.get("product")
        if not product_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload inválido para produto")
        product = state.apply_remote_product(product_payload)
        return {"status": "ok", "product": product.to_dict()}
    if tipo == "user_upsert":
        user_payload = payload.get("user")
        password_hash = payload.get("password_hash")
        if not user_payload or not password_hash:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload inválido para usuário")
        user = state.apply_remote_user(
            {
                "username": user_payload["username"],
                "role": user_payload.get("role", "user"),
                "password_hash": password_hash,
                "criado_em": user_payload.get("criado_em"),
            }
        )
        return {"status": "ok", "user": user.to_dict()}
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de evento desconhecido")


# ---------------------------------------------------------------------------
# Ciclo de vida e inclusão de rotas


@app.on_event("startup")
async def startup_event() -> None:
    await synchronizer.start()
    await _ensure_admin_user()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await synchronizer.stop()


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(clients_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(inventory_router)
app.include_router(status_router)
app.include_router(replica_router)
