"""
PHANTOM ENGINE v3.0 — API + BROWSERLESS.IO (Navegador Fantasma Remoto)
Backend FastAPI com endpoints para controle via Dashboard
Usa Browserless.io para rodar Chrome na nuvem (sem precisar instalar Chrome local)

Rodar: python phantom_engine_v3_api.py
Ou:    uvicorn phantom_engine_v3_api:app --host 0.0.0.0 --port 8000
"""

import asyncio
import random
import logging
import time
import uuid
import os
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
API_TOKEN = os.environ.get("API_TOKEN", "phantom-secret-token-2024")
BROWSERLESS_API_KEY = os.environ.get("BROWSERLESS_API_KEY", "2U6j8UELt0s2v5cf9d8a4a6aeb945befbd2ce744ab310de56")
BROWSERLESS_WS_URL = f"wss://chrome.browserless.io?token={BROWSERLESS_API_KEY}"
CPF_FILE = Path("cpfs.txt")

# ─── App FastAPI ──────────────────────────────────────────────────────────────
app = FastAPI(title="PHANTOM ENGINE v3.0", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Models ──────────────────────────────────────────────────────────────────

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
    type: str

class EngineStatusResponse(BaseModel):
    id: str
    status: str
    successes: int
    failures: int
    total_attempts: int
    uptime_seconds: int
    logs: list[LogEntry]

# ─── Sessoes em memoria ─────────────────────────────────────────────────────

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

# ─── Auth ────────────────────────────────────────────────────────────────────

async def verify_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token invalido")
    token = authorization.replace("Bearer ", "")
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalido")
    return token

# ─── Helpers ─────────────────────────────────────────────────────────────────

def load_cpfs_from_file() -> list[str]:
    if not CPF_FILE.exists():
        return []
    with open(CPF_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

def get_random_user_data(cpf_list: list[str]) -> dict:
    nomes = [
        "Gabriel", "Beatriz", "Rafael", "Larissa", "Thiago", "Fernanda",
        "Bruno", "Camila", "Lucas", "Amanda", "Pedro", "Juliana",
        "Matheus", "Carolina", "Diego", "Isabela", "Gustavo", "Mariana",
        "Felipe", "Leticia", "Rodrigo", "Natalia", "Vinicius", "Aline",
    ]
    sobrenomes = [
        "Melo", "Cardoso", "Teixeira", "Almeida", "Nascimento", "Freitas",
        "Barbosa", "Oliveira", "Santos", "Pereira", "Costa", "Rodrigues",
        "Martins", "Souza", "Lima", "Ferreira", "Goncalves", "Ribeiro",
    ]
    dominios = ["@gmail.com", "@outlook.com"]

    nome = f"{random.choice(nomes)} {random.choice(sobrenomes)}"
    slug = nome.lower().replace(" ", ".") + str(random.randint(10, 999))
    email = f"{slug}{random.choice(dominios)}"
    cpf = random.choice(cpf_list) if cpf_list else "00000000000"
    ddd = random.choice(["11", "21", "31", "41", "51", "61", "67", "71", "81", "85"])
    celular = f"({ddd}) 9{random.randint(8000, 9999)}-{random.randint(1000, 9999)}"

    return {"name": nome, "email": email, "cpf": cpf, "phone": celular}

# ─── Automacao via Browserless.io (Chrome Remoto na Nuvem) ──────────────────

async def run_checkout_session(session: EngineSession, proxy: str, user_data: dict):
    """Executa uma sessao de checkout usando Browserless.io (Chrome remoto)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        session.add_log("Playwright nao instalado! Rode: pip install playwright", "error")
        session.failures += 1
        return False

    async with async_playwright() as p:
        session.add_log(f"Conectando ao Browserless.io (Chrome remoto na nuvem)...", "info")
        try:
            # Conecta ao Chrome remoto do Browserless.io via WebSocket
            # O proxy e configurado no nivel do Browserless
            browser = await p.chromium.connect_over_cdp(BROWSERLESS_WS_URL)

            context = await browser.new_context(
                user_agent=random.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                ]),
                viewport={"width": random.choice([1366, 1440, 1920]), "height": random.choice([768, 900, 1080])},
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
            )
            page = await context.new_page()

            session.add_log(f"Navegando para: {session.payload.target_url}", "info")
            await page.goto(session.payload.target_url, wait_until="networkidle", timeout=60000)

            # Simula comportamento humano com delays aleatorios
            await asyncio.sleep(random.uniform(1.5, 3.0))

            # --- ETAPA 1: DADOS PESSOAIS ---
            session.add_log(f"Preenchendo: {user_data['name']} | {user_data['email']}", "info")

            # Preenche Nome com digitacao humana
            name_field = page.locator('input#name, input[name="name"]').first
            await name_field.click()
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await name_field.fill("")
            await name_field.type(user_data["name"], delay=random.randint(50, 120))

            await asyncio.sleep(random.uniform(0.5, 1.0))

            # Preenche Email
            email_field = page.locator('input#email, input[name="email"]').first
            await email_field.click()
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await email_field.fill("")
            await email_field.type(user_data["email"], delay=random.randint(40, 100))

            await asyncio.sleep(random.uniform(0.5, 1.0))

            # Preenche Celular
            phone_field = page.locator('input#phone, input[name="phone"]').first
            await phone_field.click()
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await phone_field.fill("")
            # Remove parenteses e tracos para digitar apenas numeros
            phone_digits = user_data["phone"].replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
            await phone_field.type(phone_digits, delay=random.randint(50, 120))

            await asyncio.sleep(random.uniform(0.8, 1.5))

            # Clica em CONTINUAR (Etapa 1)
            session.add_log("Clicando em CONTINUAR (Dados Pessoais)...", "info")
            continuar_btn = page.locator('button#next-button-dados-pessoais, button:has-text("CONTINUAR")').first
            await continuar_btn.click()

            await asyncio.sleep(random.uniform(2.0, 4.0))

            # --- ETAPA 2: ENTREGA (CPF + CEP) ---
            session.add_log("Aguardando campos de entrega (CPF)...", "info")

            try:
                cpf_field = page.locator('input#cpf, input[name="cpf"], input[placeholder*="CPF"]').first
                await cpf_field.wait_for(state="visible", timeout=15000)
                await cpf_field.click()
                await asyncio.sleep(random.uniform(0.3, 0.8))
                await cpf_field.fill("")
                cpf_digits = user_data["cpf"].replace(".", "").replace("-", "").replace(" ", "")
                await cpf_field.type(cpf_digits, delay=random.randint(50, 120))
                session.add_log(f"CPF preenchido: {cpf_digits[:3]}.***.***-**", "info")
            except Exception as e:
                session.add_log(f"Campo CPF nao encontrado ou erro: {str(e)[:80]}", "error")

            await asyncio.sleep(random.uniform(0.5, 1.0))

            # Tenta preencher CEP se existir
            try:
                cep_field = page.locator('input#cep, input[name="cep"], input[name="zipcode"], input[placeholder*="CEP"]').first
                if await cep_field.is_visible(timeout=3000):
                    ceps_exemplo = ["01001000", "20040020", "30130000", "40020000", "50010000", "60060000", "70040900", "80010000"]
                    cep = random.choice(ceps_exemplo)
                    await cep_field.click()
                    await cep_field.fill("")
                    await cep_field.type(cep, delay=random.randint(50, 100))
                    session.add_log(f"CEP preenchido: {cep}", "info")
                    await asyncio.sleep(random.uniform(2.0, 4.0))
            except Exception:
                pass

            # Tenta preencher Numero do endereco se existir
            try:
                numero_field = page.locator('input#number, input[name="number"], input[name="addressNumber"], input[placeholder*="mero"]').first
                if await numero_field.is_visible(timeout=3000):
                    numero = str(random.randint(10, 999))
                    await numero_field.click()
                    await numero_field.fill("")
                    await numero_field.type(numero, delay=random.randint(50, 100))
                    session.add_log(f"Numero preenchido: {numero}", "info")
            except Exception:
                pass

            await asyncio.sleep(random.uniform(1.0, 2.0))

            # Clica em CONTINUAR (Etapa 2)
            session.add_log("Clicando em CONTINUAR (Entrega)...", "info")
            try:
                continuar_btn2 = page.locator('button#next-button-entrega, button:has-text("CONTINUAR")').first
                await continuar_btn2.click()
            except Exception:
                # Tenta clicar em qualquer botao de continuar visivel
                buttons = page.locator('button:has-text("CONTINUAR"), button:has-text("Continuar"), button[type="submit"]')
                count = await buttons.count()
                if count > 0:
                    await buttons.last.click()

            await asyncio.sleep(random.uniform(2.0, 4.0))

            # --- ETAPA 3: PAGAMENTO ---
            session.add_log("Verificando tela de pagamento...", "info")

            try:
                # Verifica se chegou na tela de pagamento
                await page.wait_for_selector(
                    'text="pagamento", text="Pagamento", text="PIX", text="Pix", text="pix", text="Cartao", text="Boleto"',
                    timeout=15000
                )
                session.add_log("CHECKOUT ALCANCOU A TELA DE PAGAMENTO COM SUCESSO!", "success")

                # Tenta selecionar PIX como metodo de pagamento
                try:
                    pix_option = page.locator('text="PIX", text="Pix", [data-method="pix"], label:has-text("PIX")').first
                    if await pix_option.is_visible(timeout=5000):
                        await pix_option.click()
                        session.add_log("Metodo PIX selecionado!", "info")
                        await asyncio.sleep(random.uniform(1.0, 2.0))

                        # Tenta clicar no botao final de compra
                        try:
                            buy_btn = page.locator(
                                'button:has-text("Comprar"), button:has-text("Finalizar"), '
                                'button:has-text("Pagar"), button:has-text("COMPRAR"), '
                                'button:has-text("FINALIZAR"), button:has-text("PAGAR"), '
                                'button:has-text("Gerar"), button:has-text("GERAR")'
                            ).first
                            if await buy_btn.is_visible(timeout=5000):
                                await buy_btn.click()
                                session.add_log("BOTAO DE COMPRA CLICADO! VENDA GERADA!", "success")
                                await asyncio.sleep(random.uniform(3.0, 5.0))
                        except Exception:
                            session.add_log("Botao de compra nao encontrado, mas checkout foi alcancado.", "info")
                except Exception:
                    session.add_log("PIX nao encontrado, tentando outro metodo...", "info")

                session.successes += 1
                return True

            except Exception as e:
                session.add_log(f"Nao alcancou tela de pagamento: {str(e)[:100]}", "error")
                session.failures += 1
                return False

        except Exception as e:
            session.add_log(f"Erro na sessao: {str(e)[:150]}", "error")
            session.failures += 1
            return False
        finally:
            try:
                if "context" in locals():
                    await context.close()
                if "browser" in locals() and browser.is_connected():
                    await browser.close()
            except Exception:
                pass
            session.add_log("Sessao Browserless encerrada.", "info")

# ─── Loop Principal da Engine ────────────────────────────────────────────────

async def engine_loop(session: EngineSession):
    """Loop que roda em background enquanto a sessao estiver ativa."""
    payload = session.payload

    cpf_list = payload.cpfs if payload.cpfs else load_cpfs_from_file()
    if not cpf_list:
        session.add_log("Nenhum CPF disponivel! Usando CPF generico.", "error")
        cpf_list = ["00000000000"]

    proxy_list = payload.proxies
    proxy_idx = 0
    successes_on_current_proxy = 0

    session.add_log(
        f"Engine iniciada | {len(proxy_list)} proxies | {len(cpf_list)} CPFs | "
        f"Intervalo: {payload.interval_seconds}s | Browserless.io: ATIVO",
        "info",
    )
    session.add_log(f"Rotacao de proxy a cada {payload.rotate_after_successes} sucesso(s)", "info")

    while not session._stop_event.is_set():
        proxy = proxy_list[proxy_idx]
        user_data = get_random_user_data(cpf_list)
        session.total_attempts += 1

        session.add_log(
            f"-- Sessao #{session.total_attempts} | Proxy {proxy_idx + 1}/{len(proxy_list)} --",
            "info",
        )

        success = await run_checkout_session(session, proxy, user_data)

        if success:
            successes_on_current_proxy += 1
            if successes_on_current_proxy >= payload.rotate_after_successes:
                proxy_idx = (proxy_idx + 1) % len(proxy_list)
                successes_on_current_proxy = 0
                session.add_log(f"Proxy rotacionado -> {proxy_list[proxy_idx][:30]}...", "info")
        else:
            proxy_idx = (proxy_idx + 1) % len(proxy_list)
            successes_on_current_proxy = 0
            session.add_log(f"Erro detectado, proxy rotacionado -> {proxy_list[proxy_idx][:30]}...", "info")

        session.add_log(f"Aguardando {payload.interval_seconds}s para proxima sessao...", "info")

        try:
            await asyncio.wait_for(session._stop_event.wait(), timeout=payload.interval_seconds)
            break
        except asyncio.TimeoutError:
            continue

    session.status = "stopped"
    session.add_log("Engine parada.", "info")

# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.post("/api/start")
async def api_start(payload: StartPayload, _=Depends(verify_token)):
    session_id = str(uuid.uuid4())
    session = EngineSession(session_id, payload)
    sessions[session_id] = session
    session.task = asyncio.create_task(engine_loop(session))
    log.info(f"Sessao {session_id} criada")
    return {"id": session_id}

@app.get("/api/status/{session_id}")
async def api_status(session_id: str, _=Depends(verify_token)):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")
    return session.to_response()

@app.post("/api/stop/{session_id}")
async def api_stop(session_id: str, _=Depends(verify_token)):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")

    session._stop_event.set()
    if session.task:
        session.task.cancel()
        try:
            await session.task
        except (asyncio.CancelledError, Exception):
            pass

    session.status = "stopped"
    session.add_log("Parado pelo usuario via Dashboard.", "info")
    return {"message": "Sessao parada com sucesso"}

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "engine": "PHANTOM ENGINE v3.0 (Browserless.io)",
        "browserless": "connected",
        "sessions": len(sessions),
    }

# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Iniciando PHANTOM ENGINE v3.0 — Browserless.io Mode")
    log.info(f"Browserless WS: {BROWSERLESS_WS_URL[:50]}...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
