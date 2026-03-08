# PHANTOM ENGINE v3.0 — Backend API

## Rodar Local

```bash
cd backend
pip install fastapi uvicorn pydantic playwright
playwright install chromium
python phantom_engine_v3_api.py
```

Servidor sobe em `http://localhost:8000`

## Rodar com Docker

```bash
cd backend
docker build -t phantom-engine .
docker run -p 8000:8000 phantom-engine
```

## Configurar no Dashboard

1. Abra o Dashboard → **Configurações**
2. URL Base: `http://localhost:8000` (ou IP do servidor)
3. Token: `phantom-secret-token-2024`

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/start` | Inicia sessão Playwright |
| GET | `/api/status/{id}` | Status + logs em tempo real |
| POST | `/api/stop/{id}` | Para uma sessão |
| GET | `/api/health` | Health check |

## Trocar Token

Edite `API_TOKEN` no início do `phantom_engine_v3_api.py`.
