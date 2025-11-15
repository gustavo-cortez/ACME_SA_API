from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field
from typing import List, Literal

AllowedRoles = Literal["admin", "operador", "auditor"]


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    role: AllowedRoles = "operador"


class ClientRequest(BaseModel):
    id: str | None = Field(default=None, min_length=1, description="Opcional, será gerado se omitido")
    nome: str = Field(..., min_length=2)
    documento: str | None = Field(default=None)
    email: EmailStr | None = Field(default=None)


class ProductRequest(BaseModel):
    id: str | None = Field(default=None, min_length=1, description="Opcional, será gerado se omitido")
    nome: str = Field(..., min_length=2)
    descricao: str | None = Field(default=None)
    ativo: bool = True


class PedidoItemRequest(BaseModel):
    produto_id: str = Field(..., min_length=1)
    quantidade: int = Field(..., gt=0)


class PedidoRequest(BaseModel):
    cliente_id: str = Field(..., min_length=1)
    itens: List[PedidoItemRequest] = Field(..., min_length=1)
    pedido_id: str | None = Field(default=None, description="Opcional para testes controlados")


class EstoqueUpdateRequest(BaseModel):
    variacao: int
    motivo: str | None = Field(default=None, description="Uso livre para auditoria")
