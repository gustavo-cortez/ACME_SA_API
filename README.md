

## Execução com Docker

### Build local único
```powershell
# Windows/Linux/macOS
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
  docker run --rm -p 8000:8000 \
    -e NODE_NAME=node-a \
    -e PEERS= \
    -e JWT_SECRET=acme-jwt-secret \
    -e REPLICATION_TOKEN=replica-secret \
    -e DATABASE_DIR=/data \
    -v "$(Resolve-Path .\data):/data" \
    acme-api
  ```

### Subir duas réplicas com Docker Compose
```powershell
docker-compose up -d
```
- node-a exposto em 8000, node-b em 8001 (ambos ouvindo 8000 internamente).
- Volumes data-a e data-b armazenam os bancos.

> Ajuste ADMIN_PASSWORD, JWT_SECRET e REPLICATION_TOKEN quando for para produção.

