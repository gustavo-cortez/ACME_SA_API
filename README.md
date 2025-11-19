# ACME/SA - API Distribuída de Pedidos e Estoque

API acadêmico-profissional que simula múltiplas filiais replicando pedidos e estoque. Cada nó roda FastAPI + SQLite (WAL), sincroniza eventos via HTTP e aplica autenticação JWT com usuários persistidos. Código disponível no [GitHub](https://github.com/gustavo-cortez/ACME_SA_API).

## Visão rápida
- **Domínio completo**: clientes, produtos, usuários, pedidos (itens) e estoque versionado.
- **Autenticação**: login (`/auth/login`) com bcrypt + JWT (`JWT_SECRET`), perfis admin/operador/auditor; admin seedado no startup.
- **Consistência e replicação**: locks por produto + transação única para pedido/estoque; eventos idempotentes (`client_upsert`, `product_upsert`, `user_upsert`, `order_created`, `stock_update`) entre pares configurados em `PEERS`.
- **Tolerância a falhas**: fila best-effort com retentativa (`REPLICATION_RETRY_SECONDS`); backlog visível em `/status`.
- **Segurança interna**: tráfego entre réplicas protegido por `X-Replica-Token` separado dos tokens de usuário.

## Organização de pastas

```
📦 
├─ .gitignore
├─ Dockerfile
├─ README.md
├─ app
│  ├─ __init__.py
│  ├─ core
│  │  ├─ __init__.py
│  │  ├─ config.py
│  │  ├─ context.py
│  │  ├─ dependencies.py
│  │  ├─ http.py
│  │  ├─ replication.py
│  │  └─ security.py
│  ├─ db
│  │  ├─ __init__.py
│  │  └─ database.py
│  ├─ main.py
│  ├─ routers
│  │  ├─ __init__.py
│  │  ├─ auth.py
│  │  ├─ clientes.py
│  │  ├─ estoque.py
│  │  ├─ pedidos.py
│  │  ├─ produtos.py
│  │  ├─ replica.py
│  │  ├─ status.py
│  │  └─ users.py
│  ├─ schemas
│  │  └─ __init__.py
│  └─ services
│     ├─ __init__.py
│     └─ inventory.py
├─ docker-compose.yml
├─ docs
│  └─ Relatorio.pdf
└─ requirements.txt
```

## Requisitos
- Python 3.11+
- Pip
- Docker (Opcional)

## Variáveis de ambiente principais
| Nome | Descrição | Padrão |
| --- | --- | --- |
| `NODE_NAME` | Identificação do nó | `node-a` |
| `PEERS` | URLs dos pares (`,` separado) | vazio |
| `JWT_SECRET` | Segredo dos tokens JWT | `acme-jwt-secret` |
| `ADMIN_USER` / `ADMIN_PASSWORD` | Usuário admin inicial | `admin` / `admin123` |
| `REPLICATION_TOKEN` | Segredo para `/replica/event` | `replica-secret` |
| `DATABASE_DIR` | Pasta dos arquivos `.db` | `data` |
| `REPLICATION_RETRY_SECONDS` | Intervalo de retentativa | `10` |

## Rodando local (venv)
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Configure as variáveis no terminal antes do `uvicorn` conforme necessário.

## Execução com Docker
### Build local único
```powershell
docker build -t acme-api .
```

### Rodar um nó (porta 8000)
- Linux/macOS:
  ```bash
  docker run --rm -p 8000:8000 \
    -e NODE_NAME=node-a \
    -e PEERS= \
    -e JWT_SECRET=acme-jwt-secret \
    -e REPLICATION_TOKEN=replica-secret \
    -e DATABASE_DIR=/data \
    -v "$(pwd)/data:/data" \
    acme-api
  ```
- Windows (PowerShell):
  ```powershell
  docker run --rm -p 8000:8000 ^
    -e NODE_NAME=node-a ^
    -e PEERS= ^
    -e JWT_SECRET=acme-jwt-secret ^
    -e REPLICATION_TOKEN=replica-secret ^
    -e DATABASE_DIR=/data ^
    -v "$(Resolve-Path .\data):/data" ^
    acme-api
  ```

### Duas réplicas com Docker Compose
```powershell
docker-compose up -d
```
- node-a exposto em 8000, node-b em 8001 (ambos ouvindo 8000 internamente).
- Volumes `data-a` e `data-b` armazenam os bancos.

> Ajuste `ADMIN_PASSWORD`, `JWT_SECRET` e `REPLICATION_TOKEN` antes de produção.

## Endpoints principais
Todos os `POST`/`PUT` aceitam `application/json` e `application/x-www-form-urlencoded` (mesmo schema). Para formulários com listas (itens do pedido), envie `itens` em JSON string.

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/auth/login` | JWT. |
| `POST` | `/usuarios` | Cria usuário (admin). |
| `GET` | `/usuarios/me` | Dados do usuário autenticado. |
| `POST` | `/clientes` | Cria/atualiza cliente (ID gerado no servidor). |
| `GET` | `/clientes` / `/{id}` | Lista/consulta clientes. |
| `POST` | `/produtos` | Cria/atualiza produto (ID gerado no servidor). |
| `GET` | `/produtos` / `/{id}` | Lista/consulta produtos. |
| `POST` | `/pedido` | Cria pedido para cliente existente com itens `{produto_id, quantidade}`. |
| `GET` | `/pedido/{id}` | Consulta pedido. |
| `PUT` | `/estoque/{produto}` | Ajusta saldo (entrada/saída) com replicação. |
| `GET` | `/estoque/{produto}` | Saldo + versão. |
| `GET` | `/status` | Contagens, estoque, fila por peer. |
| `POST` | `/replica/event` | Uso interno entre nós (`X-Replica-Token`). |

> Os IDs de clientes e produtos são sempre gerados pelo servidor e retornados na resposta de criação; use esses valores nas próximas requisições (ex.: `cliente_id` e `produto_id` do pedido).

### Exemplo de pedido
- JSON:
```json
{
  "cliente_id": "cli-001",
  "itens": [
    {"produto_id": "sku-123", "quantidade": 2},
    {"produto_id": "sku-456", "quantidade": 1}
  ]
}
```
- Formulário: `cliente_id=cli-001`, `itens=[{"produto_id":"sku-123","quantidade":2}]`