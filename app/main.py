from __future__ import annotations

from fastapi import FastAPI

from .core.context import settings, synchronizer
from .core.dependencies import ensure_admin_user
from .routers import auth, clientes, estoque, pedidos, produtos, replica, status, users

app = FastAPI(
    title="ACME/SA - Plataforma Distribuída",
    version="3.3.0",
    description="Controle profissional de pedidos, estoque, clientes e usuários com replicação entre filiais.",
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(clientes.router)
app.include_router(produtos.router)
app.include_router(pedidos.router)
app.include_router(estoque.router)
app.include_router(status.router)
app.include_router(replica.router)


@app.on_event("startup")
async def startup_event() -> None:
    await synchronizer.start()
    await ensure_admin_user()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await synchronizer.stop()
