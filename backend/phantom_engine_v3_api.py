"""
╔═════════════════════════════════════════════════════════════════════════════════╗
║   PHANTOM ENGINE v3.0 — API + NAVEGADOR FANTASMA                               ║
║   Backend FastAPI com endpoints para controle via Dashboard                     ║
║                                                                                 ║
║   Rodar: python phantom_engine_v3_api.py                                       ║
║   Ou:    uvicorn phantom_engine_v3_api:app --host 0.0.0.0 --port 8000          ║
╚═════════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import random
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("phantom_engine")

# ─── Config ───────────────────────────────────────────────────────────────────
API_TOKEN = "phantom-secret-token-2024"  # Troque por um token seguro!
CPF_FILE = Path("cpfs.txt")

# ─── App FastAPI ──────────────────────────────────────────────────────────────
app = FastAPI(title="PHANTOM ENGINE v3.0", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, restrinja ao domínio do seu front
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Models (batem 100% com o front) ─────────────────────────────────────────

class StartPayload(BaseModel):
    target_url: str
    proxies: list[str] = Field(min_length=1)
    interval_seconds: int = Field(default=120, ge=1, le=3600)
    cpfs: Optional[list[str]] = None
    headless: bool = True
    rotate_after_successes: int = Field(default=1, ge=1, le=100)

class LogEntry(BaseModel):
    timestamp: str
    message: str
    type: str  # "success" | "error" | "info"

class EngineStatusResponse(BaseModel):
    id: str
    status: str  # "running" | "stopped" | "error"
    successes: int
    failures: int
    total_attempts: int
    uptime_seconds: int
    logs: list[LogEntry]

# ─── Sessões em memória ──────────────────────────────────────────────────────

class EngineSession:
    def __init__(self, session_id: str, payload: StartPayload):
        self.id = session_id
        self.payload = payload
        self.status = "running"
        self.successes = 0
        self.failures = 0
        self.total_attempts = 0
        self.start_time = time.time()
        self.logs: list[dict] = []
        self.task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def add_log(self, message: str, log_type: str = "info"):
        self.logs.append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "message": message,
            "type": log_type,
        })
        # Manter últimos 200 logs
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]
        log.info(f"[{self.id[:8]}] [{log_type}] {message}")

    @property
    def uptime_seconds(self) -> int:
        return int(time.time() - self.start_time)

    def to_response(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "successes": self.successes,
            "failures": self.failures,
            "total_attempts": self.total_attempts,
            "uptime_seconds": self.uptime_seconds,
            "logs": self.logs,
        }

sessions: dict[str, EngineSession] = {}

# ─── Auth ─────────────────────────────────────────────────────────────────────

async def verify_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token inválido")
    token = authorization.replace("Bearer ", "")
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido")
    return token

# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_cpfs_from_file() -> list[str]:
    if not CPF_FILE.exists():
        return []
    with open(CPF_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

def get_random_user_data(cpf_list: list[str]) -> dict:
    nomes = ["Gabriel", "Beatriz", "Rafael", "Larissa", "Thiago", "Fernanda", "Bruno", "Camila",
             "Lucas", "Amanda", "Pedro", "Juliana", "Matheus", "Carolina", "Diego", "Isabela"]
    sobrenomes = ["Melo", "Cardoso", "Teixeira", "Almeida", "Nascimento", "Freitas", "Barbosa",
                  "Oliveira", "Santos", "Pereira", "Costa", "Rodrigues", "Martins", "Souza"]
    dominios = ["@gmail.com", "@outlook.com", "@hotmail.com"]

    nome = f"{random.choice(nomes)} {random.choice(sobrenomes)}"
    email = f"{nome.lower().replace(' ', '_')}{random.randint(10, 99)}{random.choice(dominios)}"
    cpf = random.choice(cpf_list) if cpf_list else "00000000000"
    celular = f"(67) 9{random.randint(8000, 9999)}-{random.randint(1000, 9999)}"

    return {"name": nome, "email": email, "cpf": cpf, "phone": celular}

# ─── Automação Playwright ────────────────────────────────────────────────────

async def run_checkout_session(session: EngineSession, proxy: str, user_data: dict):
    """Executa uma sessão de checkout com Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        session.add_log("❌ Playwright não instalado! Rode: pip install playwright && playwright install chromium", "error")
        session.failures += 1
        return False

    async with async_playwright() as p:
        session.add_log(f"🚀 Iniciando navegador com proxy: {proxy[:30]}...", "info")
        try:
            browser = await p.chromium.launch(
                headless=session.payload.headless,
                proxy={"server": proxy},
            )
            context = await browser.new_context()
            page = await context.new_page()

            session.add_log(f"🌐 Navegando para: {session.payload.target_url}", "info")
            await page.goto(session.payload.target_url, timeout=60000)

            # --- ETAPA 1: DADOS PESSOAIS ---
            session.add_log(f"👤 Preenchendo dados: {user_data['name']} | {user_data['email']}", "info")
            await page.fill('input[name="name"]', user_data["name"])
            await page.fill('input[name="email"]', user_data["email"])
            await page.fill('input[name="phone"]', user_data["phone"])
            await page.click('button:has-text("CONTINUAR")')

            # --- ETAPA 2: CPF / ENTREGA ---
            session.add_log("📋 Aguardando campo CPF...", "info")
            await page.wait_for_selector('input[name="cpf"]', timeout=15000)
            await page.fill('input[name="cpf"]', user_data["cpf"])
            session.add_log(f"🆔 CPF preenchido: {user_data['cpf'][:3]}.***.***-**", "info")
            await page.click('button:has-text("CONTINUAR")')

            # --- ETAPA 3: PAGAMENTO ---
            session.add_log("💳 Aguardando tela de pagamento...", "info")
            await page.wait_for_selector('text="Opção de pagamento"', timeout=15000)
            session.add_log("✅ Checkout alcançou a tela de pagamento com sucesso!", "success")

            await asyncio.sleep(5)
            session.successes += 1
            return True

        except Exception as e:
            session.add_log(f"❌ Erro: {str(e)[:150]}", "error")
            session.failures += 1
            return False
        finally:
            if "browser" in locals() and browser.is_connected():
                await browser.close()
            session.add_log("🔒 Navegador fechado.", "info")

# ─── Loop Principal da Engine ────────────────────────────────────────────────

async def engine_loop(session: EngineSession):
    """Loop que roda em background enquanto a sessão estiver ativa."""
    payload = session.payload

    # Carregar CPFs: do payload ou do arquivo
    cpf_list = payload.cpfs if payload.cpfs else load_cpfs_from_file()
    if not cpf_list:
        session.add_log("⚠️ Nenhum CPF disponível! Usando CPF genérico.", "error")
        cpf_list = ["00000000000"]

    proxy_list = payload.proxies
    proxy_idx = 0
    successes_on_current_proxy = 0

    session.add_log(f"🏁 Engine iniciada | {len(proxy_list)} proxies | {len(cpf_list)} CPFs | Intervalo: {payload.interval_seconds}s", "info")
    session.add_log(f"🔄 Rotação de proxy a cada {payload.rotate_after_successes} sucesso(s)", "info")

    while not session._stop_event.is_set():
        proxy = proxy_list[proxy_idx]
        user_data = get_random_user_data(cpf_list)
        session.total_attempts += 1

        session.add_log(f"── Sessão #{session.total_attempts} | Proxy {proxy_idx + 1}/{len(proxy_list)} ──", "info")

        success = await run_checkout_session(session, proxy, user_data)

        if success:
            successes_on_current_proxy += 1
            if successes_on_current_proxy >= payload.rotate_after_successes:
                proxy_idx = (proxy_idx + 1) % len(proxy_list)
                successes_on_current_proxy = 0
                session.add_log(f"🔄 Proxy rotacionado → {proxy_list[proxy_idx][:30]}...", "info")
        else:
            # Em erro, rotaciona proxy imediatamente
            proxy_idx = (proxy_idx + 1) % len(proxy_list)
            successes_on_current_proxy = 0
            session.add_log(f"🔄 Erro detectado, proxy rotacionado → {proxy_list[proxy_idx][:30]}...", "info")

        session.add_log(f"⏳ Aguardando {payload.interval_seconds}s para próxima sessão...", "info")

        # Aguarda intervalo ou stop
        try:
            await asyncio.wait_for(session._stop_event.wait(), timeout=payload.interval_seconds)
            break  # stop_event foi setado
        except asyncio.TimeoutError:
            continue  # Timeout = próxima iteração

    session.status = "stopped"
    session.add_log("🛑 Engine parada.", "info")

# ─── Endpoints (batem 100% com engine-api.ts do front) ───────────────────────

@app.post("/api/start")
async def api_start(payload: StartPayload, _=Depends(verify_token)):
    session_id = str(uuid.uuid4())
    session = EngineSession(session_id, payload)
    sessions[session_id] = session

    # Inicia loop em background
    session.task = asyncio.create_task(engine_loop(session))

    log.info(f"✅ Sessão {session_id} criada")
    return {"id": session_id}

@app.get("/api/status/{session_id}")
async def api_status(session_id: str, _=Depends(verify_token)):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return session.to_response()

@app.post("/api/stop/{session_id}")
async def api_stop(session_id: str, _=Depends(verify_token)):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    session._stop_event.set()
    if session.task:
        session.task.cancel()
        try:
            await session.task
        except (asyncio.CancelledError, Exception):
            pass

    session.status = "stopped"
    session.add_log("🛑 Parado pelo usuário via Dashboard.", "info")

    return {"message": "Sessão parada com sucesso"}

@app.get("/api/health")
async def health():
    return {"status": "ok", "engine": "PHANTOM ENGINE v3.0", "sessions": len(sessions)}

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("🚀 Iniciando PHANTOM ENGINE v3.0 — API Mode")
    uvicorn.run(app, host="0.0.0.0", port=8000)
