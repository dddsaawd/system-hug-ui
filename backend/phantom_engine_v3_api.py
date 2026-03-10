"""
PHANTOM ENGINE v3.5 — UNIVERSAL CHECKOUT ENGINE
Backend FastAPI + Browserless.io (Chrome Remoto na Nuvem)
Detecta automaticamente campos e botoes de QUALQUER checkout.
Suporta fluxos de 3 a 5 etapas (Corvex, CartPanda, Yampi, etc.)

Rodar: python phantom_engine_v3_api.py
Ou:    uvicorn phantom_engine_v3_api:app --host 0.0.0.0 --port 8000
"""

import asyncio
import random
import logging
import time
import uuid
import os
import re
import json
import subprocess
import httpx
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
ENGINE_MODE = os.environ.get("ENGINE_MODE", "local")
BROWSERLESS_API_KEY = os.environ.get("BROWSERLESS_API_KEY", "")
BROWSERLESS_BASE_URL = f"wss://chrome.browserless.io?token={BROWSERLESS_API_KEY}&timeout=30000"

# Garante que o Playwright encontre os browsers no path correto
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright")

CPF_FILE = Path("cpfs.txt")

# ─── App FastAPI ──────────────────────────────────────────────────────────────
app = FastAPI(title="PHANTOM ENGINE v4.0 UNIVERSAL", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Health Check (testa Chromium) ────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Testa se o Chromium consegue iniciar corretamente."""
    import glob
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright")
    found_files = glob.glob(f"{browsers_path}/**/chrome*", recursive=True)
    
    chromium_ok = False
    error_msg = None
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                timeout=30000,
            )
            version = browser.version
            await browser.close()
            chromium_ok = True
    except Exception as e:
        error_msg = str(e)
    
    return {
        "status": "ok" if chromium_ok else "error",
        "chromium": chromium_ok,
        "chromium_version": version if chromium_ok else None,
        "error": error_msg,
        "browsers_path": browsers_path,
        "found_binaries": found_files[:10],
        "engine_mode": ENGINE_MODE,
    }



class DirectApiConfig(BaseModel):
    platform: str = "zedy"
    token: str = ""
    store_id: Optional[int] = None
    checkout_id: Optional[int] = None
    payment_method: str = "pix"
    zipcode: Optional[str] = None

class StartPayload(BaseModel):
    target_url: str
    proxies: list[str] = Field(default=[])
    interval_seconds: int = Field(default=120, ge=1, le=3600)
    cpfs: Optional[list[str]] = None
    headless: bool = True
    rotate_after_successes: int = Field(default=1, ge=1, le=100)
    is_product_url: bool = Field(default=False)
    capture_network: bool = Field(default=False)
    engine_mode: str = Field(default="browser")  # "browser" or "direct_api"
    direct_api_config: Optional[DirectApiConfig] = None

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
        self.captured_requests: list[dict] = []  # Network capture

    def add_log(self, message: str, log_type: str = "info"):
        self.logs.append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "message": message,
            "type": log_type,
        })
        if len(self.logs) > 500:
            self.logs = self.logs[-500:]
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
            "captured_requests": self.captured_requests[-100:],  # últimas 100
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
        "Leonardo", "Bianca", "Henrique", "Patricia", "Marcos", "Daniela",
        "Andre", "Priscila", "Eduardo", "Vanessa", "Joao", "Renata",
        "Carlos", "Tatiana", "Marcelo", "Simone", "Alexandre", "Adriana",
    ]
    sobrenomes = [
        "Melo", "Cardoso", "Teixeira", "Almeida", "Nascimento", "Freitas",
        "Barbosa", "Oliveira", "Santos", "Pereira", "Costa", "Rodrigues",
        "Martins", "Souza", "Lima", "Ferreira", "Goncalves", "Ribeiro",
        "Araujo", "Carvalho", "Monteiro", "Moreira", "Vieira", "Nunes",
        "Mendes", "Pinto", "Correia", "Dias", "Ramos", "Lopes",
    ]
    dominios = ["@gmail.com", "@outlook.com"]

    nome = f"{random.choice(nomes)} {random.choice(sobrenomes)}"
    slug = nome.lower().replace(" ", ".") + str(random.randint(10, 999))
    email = f"{slug}{random.choice(dominios)}"
    cpf = random.choice(cpf_list) if cpf_list else "00000000000"
    ddd = random.choice(["11", "21", "31", "41", "51", "61", "67", "71", "81", "85"])
    celular = f"{ddd}9{random.randint(8000, 9999)}{random.randint(1000, 9999)}"

    return {"name": nome, "email": email, "cpf": cpf, "phone": celular}

def get_random_address() -> dict:
    """Gera um endereco brasileiro aleatorio."""
    enderecos = [
        {"cep": "01001000", "rua": "Praca da Se", "bairro": "Se", "cidade": "Sao Paulo", "estado": "SP"},
        {"cep": "20040020", "rua": "Rua do Ouvidor", "bairro": "Centro", "cidade": "Rio de Janeiro", "estado": "RJ"},
        {"cep": "30130000", "rua": "Avenida Afonso Pena", "bairro": "Centro", "cidade": "Belo Horizonte", "estado": "MG"},
        {"cep": "40020000", "rua": "Rua Chile", "bairro": "Comercio", "cidade": "Salvador", "estado": "BA"},
        {"cep": "50010000", "rua": "Avenida Guararapes", "bairro": "Santo Antonio", "cidade": "Recife", "estado": "PE"},
        {"cep": "60060000", "rua": "Rua Floriano Peixoto", "bairro": "Centro", "cidade": "Fortaleza", "estado": "CE"},
        {"cep": "70040900", "rua": "Esplanada dos Ministerios", "bairro": "Zona Civica", "cidade": "Brasilia", "estado": "DF"},
        {"cep": "80010000", "rua": "Rua XV de Novembro", "bairro": "Centro", "cidade": "Curitiba", "estado": "PR"},
        {"cep": "90010000", "rua": "Rua dos Andradas", "bairro": "Centro Historico", "cidade": "Porto Alegre", "estado": "RS"},
        {"cep": "79002000", "rua": "Rua 14 de Julho", "bairro": "Centro", "cidade": "Campo Grande", "estado": "MS"},
    ]
    addr = random.choice(enderecos)
    addr["numero"] = str(random.randint(10, 999))
    addr["complemento"] = random.choice(["", "Apto 101", "Bloco B", "Casa 2", "Sala 5", ""])
    return addr


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCOES UNIVERSAIS DE DETECCAO DE CAMPOS E BOTOES v3.5
# ═══════════════════════════════════════════════════════════════════════════════

async def smart_fill_field(page, selectors: list[str], value: str, field_name: str, session: EngineSession) -> bool:
    """Tenta preencher um campo usando multiplos seletores. Retorna True se preencheu."""
    for selector in selectors:
        try:
            field = page.locator(selector).first
            if await field.is_visible(timeout=500):
                # Verifica se o campo ja tem valor (auto-preenchido pelo CEP)
                current_val = await field.input_value() if await field.count() > 0 else ""
                if current_val and len(current_val.strip()) > 2 and field_name in ("Rua", "Bairro", "Cidade", "Estado"):
                    session.add_log(f"  {field_name}: ja preenchido = '{current_val[:30]}'", "info")
                    return True
                await field.click()
                await asyncio.sleep(random.uniform(0.05, 0.15))
                await field.fill("")
                await asyncio.sleep(random.uniform(0.03, 0.08))
                await field.fill(value)
                await asyncio.sleep(random.uniform(0.1, 0.25))
                display = value[:30] + "..." if len(value) > 30 else value
                session.add_log(f"  {field_name}: {display}", "info")
                return True
        except Exception:
            continue
    return False


async def smart_fill_field_by_label(page, label_texts: list[str], value: str, field_name: str, session: EngineSession) -> bool:
    """Tenta preencher campo buscando pelo texto do label associado."""
    for label_text in label_texts:
        try:
            # Busca input proximo a um label com o texto
            field = page.get_by_label(label_text, exact=False).first
            if await field.is_visible(timeout=500):
                current_val = ""
                try:
                    current_val = await field.input_value()
                except Exception:
                    pass
                if current_val and len(current_val.strip()) > 2 and field_name in ("Rua", "Bairro", "Cidade", "Estado"):
                    session.add_log(f"  {field_name}: ja preenchido = '{current_val[:30]}'", "info")
                    return True
                await field.click()
                await asyncio.sleep(random.uniform(0.05, 0.15))
                await field.fill("")
                await asyncio.sleep(random.uniform(0.03, 0.08))
                await field.fill(value)
                await asyncio.sleep(random.uniform(0.1, 0.25))
                display = value[:30] + "..." if len(value) > 30 else value
                session.add_log(f"  {field_name} (label): {display}", "info")
                return True
        except Exception:
            continue
    return False


async def universal_click_button(page, session: EngineSession, etapa: int) -> bool:
    """
    Clica no botao de avancar/finalizar da etapa atual.
    Estrategia otimizada: busca rapida por texto, depois fallback.
    """
    # Textos ordenados por prioridade (checkouts Texano + Imperio + genéricos)
    button_texts = [
        # Finalizacao
        "Gerar Pix", "GERAR PIX",
        "Finalizar compra", "FINALIZAR COMPRA",
        "Finalizar pedido", "FINALIZAR PEDIDO",
        "Comprar agora", "COMPRAR AGORA",
        "Pagar agora", "PAGAR AGORA",
        "Concluir compra", "CONCLUIR COMPRA",
        "Confirmar pedido", "CONFIRMAR PEDIDO",
        "Gerar Boleto", "GERAR BOLETO",
        # Navegacao
        "Ir para Pagamento", "IR PARA PAGAMENTO", "Ir para pagamento",
        "Ir para o pagamento", "IR PARA O PAGAMENTO",
        "Escolher frete", "ESCOLHER FRETE", "Escolher Frete",
        "Ir para entrega", "IR PARA ENTREGA",
        # Genéricos
        "CONTINUAR", "Continuar", "Continue",
        "Próximo", "PRÓXIMO", "Proximo", "PROXIMO",
        "Avançar", "AVANÇAR", "Avancar",
        "Prosseguir", "PROSSEGUIR",
        "Next", "NEXT",
    ]

    # ─── Estrategia 1: getByRole('button') — mais confiavel e rapido ───
    for text in button_texts:
        try:
            btn = page.get_by_role("button", name=text, exact=False).first
            if await btn.is_visible(timeout=300):
                btn_text = (await btn.text_content() or "").strip().lower()
                if any(w in btn_text for w in ["voltar", "back", "cancelar", "editar"]):
                    continue
                await btn.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(0.1, 0.25))
                await btn.click(timeout=5000)
                session.add_log(f"  Botao '{text}' clicado!", "success")
                return True
        except Exception:
            continue

    # ─── Estrategia 2: CSS selector button/a com has-text ───
    for text in button_texts:
        for tag in ["button", "a"]:
            try:
                el = page.locator(f'{tag}:has-text("{text}")').first
                if await el.is_visible(timeout=300):
                    el_text = (await el.text_content() or "").strip().lower()
                    if any(w in el_text for w in ["voltar", "back", "cancelar", "editar"]):
                        continue
                    await el.scroll_into_view_if_needed()
                    await asyncio.sleep(random.uniform(0.1, 0.25))
                    await el.click(timeout=5000)
                    session.add_log(f"  Botao <{tag}> '{text}' clicado!", "success")
                    return True
            except Exception:
                continue

    # ─── Estrategia 3: button[type=submit] visivel ───
    try:
        submit_btns = page.locator('button[type="submit"]')
        count = await submit_btns.count()
        for i in range(count):
            btn = submit_btns.nth(i)
            if await btn.is_visible(timeout=500):
                btn_text = (await btn.text_content() or "").strip()
                if btn_text and not any(w in btn_text.lower() for w in ["voltar", "back", "cancelar"]):
                    await btn.scroll_into_view_if_needed()
                    await asyncio.sleep(random.uniform(0.1, 0.25))
                    await btn.click(timeout=5000)
                    session.add_log(f"  Submit '{btn_text[:40]}' clicado!", "success")
                    return True
    except Exception:
        pass

    # ─── Estrategia 4: qualquer button visivel (fallback) ───
    try:
        all_btns = page.locator("button")
        count = await all_btns.count()
        skip_words = ["voltar", "back", "cancelar", "fechar", "close", "editar", "edit"]
        for i in range(count):
            btn = all_btns.nth(i)
            if await btn.is_visible(timeout=300):
                btn_text = (await btn.text_content() or "").strip()
                if btn_text and len(btn_text) > 2:
                    if not any(w in btn_text.lower() for w in skip_words):
                        await btn.scroll_into_view_if_needed()
                        await asyncio.sleep(random.uniform(0.1, 0.25))
                        await btn.click(timeout=5000)
                        session.add_log(f"  Fallback '{btn_text[:40]}' clicado!", "success")
                        return True
    except Exception:
        pass

    # ─── Debug: listar botoes visiveis ───
    try:
        all_btns = page.locator("button")
        count = await all_btns.count()
        visible_texts = []
        for i in range(min(count, 10)):
            btn = all_btns.nth(i)
            try:
                if await btn.is_visible(timeout=200):
                    txt = (await btn.text_content() or "").strip()[:30]
                    if txt:
                        visible_texts.append(txt)
            except Exception:
                pass
        if visible_texts:
            session.add_log(f"  DEBUG botoes visiveis: {visible_texts}", "info")
        else:
            session.add_log(f"  DEBUG: nenhum botao visivel na pagina", "info")
    except Exception:
        pass

    session.add_log(f"  ERRO: Nenhum botao encontrado na etapa {etapa}!", "error")
    return False


async def smart_select_country_brazil(page, session: EngineSession) -> bool:
    """Tenta selecionar Brasil (+55) no seletor de pais."""
    try:
        country_btn = page.locator('button[role="combobox"]').first
        if await country_btn.is_visible(timeout=2000):
            current_text = (await country_btn.text_content()) or ""
            if "+55" in current_text or "Brasil" in current_text:
                session.add_log("  Pais Brasil (+55) ja selecionado", "info")
                return True
            await country_btn.click()
            await asyncio.sleep(random.uniform(0.3, 0.6))
            for sel in ['button:has-text("Brasil")', 'button:has-text("Brazil")',
                        '[data-country="BR"]', 'li:has-text("Brasil")',
                        'option:has-text("Brasil")', 'div:has-text("+55")']:
                try:
                    brasil = page.locator(sel).first
                    if await brasil.is_visible(timeout=1500):
                        await brasil.click()
                        session.add_log("  Pais Brasil (+55) selecionado!", "info")
                        await asyncio.sleep(random.uniform(0.2, 0.4))
                        return True
                except Exception:
                    continue
            await page.keyboard.press("Escape")
    except Exception:
        pass
    return False


async def select_pix_payment(page, session: EngineSession) -> bool:
    """Tenta selecionar PIX como metodo de pagamento."""
    pix_selectors = [
        'label:has-text("PIX")', 'label:has-text("Pix")',
        'div:has-text("PIX"):not(h1):not(h2):not(h3):not(p)',
        'button:has-text("PIX")', 'button:has-text("Pix")',
        '[data-method="pix"]', '[data-payment="pix"]',
        'input[value="pix"]', 'input[value="PIX"]',
        'span:has-text("PIX")',
    ]
    for sel in pix_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1500):
                # Verifica se ja esta selecionado
                try:
                    is_checked = await el.locator('input[type="radio"]').first.is_checked()
                    if is_checked:
                        session.add_log("  PIX ja selecionado!", "info")
                        return True
                except Exception:
                    pass
                await el.click()
                session.add_log("  Metodo PIX selecionado!", "success")
                await asyncio.sleep(random.uniform(0.3, 0.6))
                return True
        except Exception:
            continue
    return False


async def select_shipping_option(page, session: EngineSession) -> bool:
    """Tenta selecionar uma opcao de frete (primeira disponivel)."""
    # Primeiro tenta radios de shipping (mais confiável)
    radio_selectors = [
        'input[name="shipping"]', 'input[name="frete"]',
        'input[name="shipping_method"]', 'input[name="delivery"]',
        '[class*="shipping"] input[type="radio"]',
        '[class*="frete"] input[type="radio"]',
        '[class*="delivery"] input[type="radio"]',
    ]
    for sel in radio_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1000):
                await el.click()
                session.add_log(f"  Frete radio clicado: {sel}", "success")
                await asyncio.sleep(random.uniform(0.3, 0.6))
                return True
        except Exception:
            continue

    # Labels com texto específico de frete (evita sidebar)
    frete_labels = [
        'label:has-text("JADLOG")', 'label:has-text("Correios")',
        'label:has-text("PAC")', 'label:has-text("SEDEX")',
        'label:has-text("Frete Grátis")', 'label:has-text("Frete grátis")',
        'label:has-text("Frete Gratis")',
        'label:has-text("Envio")',
    ]
    for sel in frete_labels:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1000):
                text = (await el.text_content() or "")[:50]
                # Evita clicar em elementos da sidebar (texto longo com "PAGAMENTO" etc)
                if "pagamento" in text.lower() or "seguro" in text.lower():
                    continue
                await el.click()
                session.add_log(f"  Frete selecionado: {text}", "success")
                await asyncio.sleep(random.uniform(0.3, 0.6))
                return True
        except Exception:
            continue
    
    return False


async def select_state_dropdown(page, estado: str, session: EngineSession) -> bool:
    """Tenta selecionar estado em dropdown <select>."""
    select_selectors = [
        'select#state', 'select[name="state"]', 'select[name="estado"]',
        'select[name="uf"]', 'select[name="address_state"]',
    ]
    for sel in select_selectors:
        try:
            dropdown = page.locator(sel).first
            if await dropdown.is_visible(timeout=1500):
                await dropdown.select_option(value=estado)
                session.add_log(f"  Estado (select): {estado}", "info")
                return True
        except Exception:
            pass
        try:
            dropdown = page.locator(sel).first
            if await dropdown.is_visible(timeout=500):
                await dropdown.select_option(label=estado)
                session.add_log(f"  Estado (select label): {estado}", "info")
                return True
        except Exception:
            continue
    return False


async def check_success(page, session: EngineSession) -> bool:
    """Verifica se a venda foi gerada com sucesso."""
    # Primeiro tenta via seletores visuais
    sucesso_selectors = [
        'text="Pedido realizado"', 'text="pedido realizado"',
        'text="Compra realizada"', 'text="compra realizada"',
        'text="Pagamento gerado"', 'text="pagamento gerado"',
        'text="PIX gerado"', 'text="Pix gerado"', 'text="pix gerado"',
        'text="QR Code"', 'text="qr code"', 'text="QR code"',
        'text="Copia e Cola"', 'text="copia e cola"',
        'text="Copiar codigo"', 'text="Copiar código"',
        'text="Copie o código"', 'text="copie o código"',
        'text="Aguardando pagamento"', 'text="aguardando pagamento"',
        'text="Obrigado"', 'text="obrigado"',
        'text="Parabéns"', 'text="parabens"',
        'text="sucesso"', 'text="Sucesso"',
        'text="Boleto gerado"', 'text="boleto gerado"',
        'text="Pedido confirmado"', 'text="pedido confirmado"',
        'text="Pedido criado"', 'text="pedido criado"',
        'text="Pague com Pix"', 'text="pague com pix"',
        'text="Escaneie o QR"', 'text="escaneie o qr"',
        'img[alt*="qr"]', 'img[alt*="QR"]',
        'canvas', '[class*="qr"]', '[class*="pix-code"]',
    ]
    for sel in sucesso_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1000):
                session.add_log(f"VENDA GERADA! Indicador: {sel[:50]}", "success")
                return True
        except Exception:
            continue

    # Fallback: verifica texto da pagina
    try:
        page_text = await page.text_content("body")
        if page_text:
            lower = page_text.lower()
            indicadores = [
                "pix gerado", "qr code", "aguardando pagamento",
                "pedido realizado", "compra realizada", "obrigado",
                "copia e cola", "copiar codigo", "copiar código",
                "boleto gerado", "pedido confirmado", "pedido criado",
                "pague com pix", "escaneie o qr", "copie o código",
                "pagamento via pix", "código pix",
            ]
            for ind in indicadores:
                if ind in lower:
                    session.add_log(f"VENDA GERADA! Texto detectado: '{ind}'", "success")
                    return True
    except Exception:
        pass

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# MOTOR PRINCIPAL DE CHECKOUT UNIVERSAL v3.5
# Fluxo: detecta campos visiveis → preenche → clica botao → repete
# ═══════════════════════════════════════════════════════════════════════════════

async def run_checkout_session(session: EngineSession, proxy: str, user_data: dict):
    """Executa uma sessao de checkout usando Playwright local ou Browserless."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        session.add_log("Playwright nao instalado!", "error")
        session.failures += 1
        return False

    browser = None
    context = None

    async with async_playwright() as p:
        try:
            # Monta proxy config
            proxy_config = None
            if proxy and proxy.strip():
                proxy_clean = proxy.strip()
                protocol = "http"
                if "socks5://" in proxy.lower() or ":10324" in proxy:
                    protocol = "socks5"

                for prefix in ["http://", "https://", "socks5://", "socks4://", "socks5h://"]:
                    if proxy_clean.startswith(prefix):
                        proxy_clean = proxy_clean[len(prefix):]
                        break

                # Auto-detect formato ip:port:user:pass
                if "@" not in proxy_clean:
                    parts = proxy_clean.split(":")
                    if len(parts) == 4:
                        # Formato: ip:port:user:pass -> converte para user:pass@ip:port
                        ip, port, username, password = parts
                        proxy_clean = f"{username}:{password}@{ip}:{port}"
                        session.add_log(f"Proxy auto-convertido: ip:port:user:pass -> formato padrao", "info")

                if "@" in proxy_clean:
                    auth_part, server_part = proxy_clean.split("@", 1)
                    username, password = auth_part.split(":", 1)
                    proxy_config = {
                        "server": f"{protocol}://{server_part}",
                        "username": username,
                        "password": password
                    }
                else:
                    proxy_config = {"server": f"{protocol}://{proxy_clean}"}

                session.add_log(f"Proxy: {proxy_config['server']}", "info")

            # === MODO LOCAL (Chromium no servidor) ===
            if ENGINE_MODE == "local" or not BROWSERLESS_API_KEY:
                session.add_log("Iniciando Chromium local...", "info")
                launch_args = [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--disable-sync",
                    "--no-first-run",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    "--disable-features=TranslateUI",
                    "--disable-ipc-flooding-protection",
                    "--disable-hang-monitor",
                    "--disable-component-update",
                    "--disable-breakpad",
                    "--disable-component-extensions-with-background-pages",
                    "--disable-client-side-phishing-detection",
                    "--js-flags=--max-old-space-size=128",
                ]
                # Playwright local: proxy com auth deve ir no contexto, não no launch
                launch_proxy = None
                context_proxy = None
                if proxy_config:
                    if "username" in proxy_config:
                        context_proxy = proxy_config
                        session.add_log(f"Proxy com auth -> contexto", "info")
                    else:
                        launch_proxy = proxy_config
                
                # Retry launch até 3 vezes (Render free pode falhar por memória)
                browser = None
                for launch_attempt in range(3):
                    try:
                        browser = await p.chromium.launch(
                            headless=True,
                            args=launch_args,
                            proxy=launch_proxy,
                            timeout=60000,
                        )
                        break
                    except Exception as launch_err:
                        session.add_log(f"Launch tentativa {launch_attempt+1}/3 falhou: {str(launch_err)[:80]}", "error")
                        if launch_attempt < 2:
                            await asyncio.sleep(2)
                        else:
                            raise launch_err
                session.add_log("Chromium local iniciado!", "success")
            else:
                # === MODO BROWSERLESS ===
                context_proxy = None
                session.add_log("Conectando ao Browserless.io...", "info")
                ws_url = BROWSERLESS_BASE_URL
                session.add_log(f"Timeout Browserless: 30000ms", "info")
                browser = await p.chromium.connect_over_cdp(ws_url)
                session.add_log("Browserless conectado!", "success")

            # ═══ EMULAÇÃO MOBILE (layout mais simples, menos elementos ocultos) ═══
            mobile_devices = [
                {
                    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
                    "viewport": {"width": 393, "height": 852},
                    "device_scale_factor": 3,
                    "is_mobile": True,
                    "has_touch": True,
                },
                {
                    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                    "viewport": {"width": 390, "height": 844},
                    "device_scale_factor": 3,
                    "is_mobile": True,
                    "has_touch": True,
                },
                {
                    "user_agent": "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.119 Mobile Safari/537.36",
                    "viewport": {"width": 360, "height": 780},
                    "device_scale_factor": 3,
                    "is_mobile": True,
                    "has_touch": True,
                },
                {
                    "user_agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.40 Mobile Safari/537.36",
                    "viewport": {"width": 412, "height": 915},
                    "device_scale_factor": 2.625,
                    "is_mobile": True,
                    "has_touch": True,
                },
            ]
            device = random.choice(mobile_devices)
            device_name = "iPhone" if "iPhone" in device["user_agent"] else "Android"
            session.add_log(f"📱 Emulando {device_name} ({device['viewport']['width']}x{device['viewport']['height']})", "info")

            context = await browser.new_context(
                proxy=context_proxy if context_proxy else None,
                user_agent=device["user_agent"],
                viewport=device["viewport"],
                device_scale_factor=device.get("device_scale_factor", 3),
                is_mobile=device.get("is_mobile", True),
                has_touch=device.get("has_touch", True),
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
            )
            page = await context.new_page()

            # ═══ INTERCEPTADOR DE REDE ═══
            if session.payload.capture_network:
                session.add_log("🔍 Captura de rede ATIVA — interceptando requests/responses", "info")
                
                async def on_response(response):
                    """Captura responses de API (ignora assets estáticos)."""
                    try:
                        url = response.url
                        # Filtra: só APIs relevantes (ignora imagens, CSS, JS, fonts)
                        skip_ext = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.css', '.js', '.woff', '.woff2', '.ttf', '.ico', '.webp')
                        skip_domains = ('google', 'facebook', 'analytics', 'hotjar', 'gtm', 'doubleclick', 'cloudflare', 'cdn')
                        
                        if any(url.lower().endswith(ext) for ext in skip_ext):
                            return
                        if any(d in url.lower() for d in skip_domains):
                            return
                        
                        status = response.status
                        method = response.request.method
                        
                        # Só captura POST/PUT/PATCH (ações de checkout) e GETs de API
                        is_api = any(k in url.lower() for k in ['/api/', '/checkout/', '/order', '/cart', '/shipping', '/payment', '/customer', '/address', '/freight', '/frete', '/cep/', '/pix', '/boleto', '/transaction', '/v1/', '/v2/', '/graphql'])
                        is_mutation = method in ('POST', 'PUT', 'PATCH', 'DELETE')
                        
                        if not is_api and not is_mutation:
                            return
                        
                        # Captura request body
                        req_body = None
                        try:
                            req_body = response.request.post_data
                        except Exception:
                            pass
                        
                        # Captura response body (só JSON)
                        res_body = None
                        content_type = response.headers.get('content-type', '')
                        if 'json' in content_type or 'text' in content_type:
                            try:
                                res_body = await response.text()
                                if len(res_body) > 5000:
                                    res_body = res_body[:5000] + "... (truncado)"
                            except Exception:
                                pass
                        
                        # Captura headers relevantes
                        req_headers = {}
                        try:
                            all_headers = response.request.headers
                            for k, v in all_headers.items():
                                kl = k.lower()
                                if kl in ('authorization', 'x-api-key', 'x-token', 'x-csrf-token', 'x-requested-with', 'content-type', 'accept', 'cookie', 'x-session-id', 'x-cart-id', 'x-checkout-id'):
                                    req_headers[k] = v
                        except Exception:
                            pass
                        
                        captured = {
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "method": method,
                            "url": url,
                            "status": status,
                            "request_headers": req_headers,
                            "request_body": req_body,
                            "response_body": res_body,
                            "content_type": content_type,
                        }
                        
                        session.captured_requests.append(captured)
                        if len(session.captured_requests) > 200:
                            session.captured_requests = session.captured_requests[-200:]
                        
                        # Log resumido
                        body_preview = ""
                        if req_body:
                            body_preview = f" | body: {req_body[:80]}"
                        session.add_log(f"  🌐 {method} {status} {url[:80]}{body_preview}", "info")
                        
                    except Exception:
                        pass
                
                page.on("response", on_response)

            # Navega para o checkout (ou produto -> carrinho -> checkout)
            session.add_log(f"Navegando: {session.payload.target_url}", "info")
            await page.goto(session.payload.target_url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(random.uniform(2.0, 3.5))

            # ═══ PRE-CHECKOUT: Produto → Carrinho → Checkout ═══
            if session.payload.is_product_url:
                session.add_log("Modo PRODUTO ativo. Buscando botao de compra...", "info")
                
                buy_btn_selectors = [
                    'button:has-text("Comprar")',
                    'button:has-text("COMPRAR")',
                    'button:has-text("Adicionar")',
                    'button:has-text("ADICIONAR")',
                    'button:has-text("Add to cart")',
                    'button:has-text("Comprar agora")',
                    'button:has-text("COMPRAR AGORA")',
                    'a:has-text("Comprar")',
                    'a:has-text("COMPRAR")',
                    '[data-action="buy"]',
                    '[data-action="add-to-cart"]',
                    '.buy-button',
                    '.btn-buy',
                    '#buy-button',
                    'input[type="submit"][value*="Comprar"]',
                ]
                
                buy_clicked = False
                for sel in buy_btn_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=1500):
                            await el.click()
                            buy_clicked = True
                            session.add_log(f"Botao de compra clicado: {sel}", "success")
                            break
                    except Exception:
                        continue
                
                if not buy_clicked:
                    session.add_log("Nao encontrou botao de compra na pagina do produto!", "error")
                    session.failures += 1
                    return False
                
                await asyncio.sleep(random.uniform(2.0, 4.0))
                
                # Verifica se foi pro carrinho ou direto pro checkout
                current_url = page.url.lower()
                if "cart" in current_url or "carrinho" in current_url:
                    session.add_log("Pagina do carrinho detectada. Buscando botao de checkout...", "info")
                    
                    checkout_btn_selectors = [
                        'button:has-text("Finalizar")',
                        'button:has-text("FINALIZAR")',
                        'button:has-text("Checkout")',
                        'button:has-text("CHECKOUT")',
                        'button:has-text("Fechar pedido")',
                        'button:has-text("FECHAR PEDIDO")',
                        'button:has-text("Continuar")',
                        'button:has-text("CONTINUAR")',
                        'button:has-text("Ir para pagamento")',
                        'a:has-text("Finalizar")',
                        'a:has-text("Checkout")',
                        'a:has-text("Fechar pedido")',
                        'a[href*="checkout"]',
                        '.checkout-button',
                        '.btn-checkout',
                        '#checkout-button',
                    ]
                    
                    checkout_clicked = False
                    for sel in checkout_btn_selectors:
                        try:
                            el = page.locator(sel).first
                            if await el.is_visible(timeout=1500):
                                await el.click()
                                checkout_clicked = True
                                session.add_log(f"Botao de checkout clicado: {sel}", "success")
                                break
                        except Exception:
                            continue
                    
                    if not checkout_clicked:
                        session.add_log("Nao encontrou botao de checkout no carrinho!", "error")
                        session.failures += 1
                        return False
                    
                    await asyncio.sleep(random.uniform(2.0, 4.0))
                    await page.wait_for_load_state("networkidle", timeout=30000)
                
                elif "checkout" in current_url:
                    session.add_log("Redirecionado direto para checkout!", "success")
                else:
                    # Pode ter aberto um modal ou ficado na mesma pagina
                    session.add_log(f"URL apos clique: {page.url[:80]}. Aguardando redirecionamento...", "info")
                    await asyncio.sleep(3.0)
                    current_url = page.url.lower()
                    if "checkout" not in current_url and "cart" not in current_url:
                        # Tenta encontrar link de checkout na pagina
                        try:
                            checkout_link = page.locator('a[href*="checkout"]').first
                            if await checkout_link.is_visible(timeout=2000):
                                await checkout_link.click()
                                session.add_log("Link de checkout encontrado e clicado!", "success")
                                await asyncio.sleep(2.0)
                                await page.wait_for_load_state("networkidle", timeout=30000)
                        except Exception:
                            pass
                
                session.add_log(f"Checkout URL: {page.url[:100]}", "info")
                await asyncio.sleep(random.uniform(1.0, 2.0))

            addr = get_random_address()
            cpf_digits = user_data["cpf"].replace(".", "").replace("-", "").replace(" ", "")

            # ═══════════════════════════════════════════════════════════
            # PHANTOM ENGINE v5.5 — DOM-INTELLIGENCE CHECKOUT
            # Extrai contexto completo de cada campo via JS no DOM
            # Scoring inteligente para identificar campos com precisão
            # Funciona em QUALQUER checkout sem configuração
            # ═══════════════════════════════════════════════════════════

            # ─── JS que extrai metadados ricos de TODOS os inputs visíveis ───
            EXTRACT_FIELDS_JS = """() => {
                const results = [];
                const inputs = document.querySelectorAll('input, textarea, select');
                
                for (const el of inputs) {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    
                    // Só campos visíveis
                    if (rect.width === 0 || rect.height === 0) continue;
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
                    if (el.disabled || el.readOnly) continue;
                    
                    const type = (el.type || el.tagName.toLowerCase()).toLowerCase();
                    if (['hidden', 'submit', 'button', 'file', 'image', 'reset'].includes(type)) continue;
                    
                    // Coleta contexto rico
                    const name = (el.name || '').toLowerCase();
                    const id = (el.id || '').toLowerCase();
                    const placeholder = (el.placeholder || '').toLowerCase();
                    const autocomplete = (el.autocomplete || '').toLowerCase();
                    const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
                    const dataTestId = (el.getAttribute('data-testid') || el.getAttribute('data-test') || '').toLowerCase();
                    
                    // Label associado
                    let labelText = '';
                    if (el.id) {
                        const label = document.querySelector('label[for="' + el.id + '"]');
                        if (label) labelText = label.textContent.trim().toLowerCase();
                    }
                    if (!labelText) {
                        const parent = el.closest('label');
                        if (parent) labelText = parent.textContent.trim().toLowerCase();
                    }
                    
                    // Texto próximo (pai imediato e irmãos)
                    let nearbyText = '';
                    const parentEl = el.parentElement;
                    if (parentEl) {
                        // Texto do container pai (sem inputs filhos)
                        const clone = parentEl.cloneNode(true);
                        clone.querySelectorAll('input, textarea, select').forEach(i => i.remove());
                        nearbyText = clone.textContent.trim().toLowerCase().substring(0, 100);
                    }
                    // Irmão anterior (frequente em forms)
                    const prev = el.previousElementSibling;
                    if (prev && prev.tagName !== 'INPUT') {
                        nearbyText += ' ' + (prev.textContent || '').trim().toLowerCase().substring(0, 50);
                    }
                    
                    // Valor atual
                    const value = el.value || '';
                    const isSelect = el.tagName === 'SELECT';
                    const isCheckbox = type === 'checkbox';
                    const isRadio = type === 'radio';
                    
                    // Classe CSS (para contexto adicional)
                    const className = (el.className || '').toLowerCase();
                    
                    // Índice para referência
                    el.setAttribute('data-phantom-idx', results.length.toString());
                    
                    results.push({
                        idx: results.length,
                        tag: el.tagName.toLowerCase(),
                        type: type,
                        name: name,
                        id: id,
                        placeholder: placeholder,
                        autocomplete: autocomplete,
                        ariaLabel: ariaLabel,
                        labelText: labelText,
                        nearbyText: nearbyText,
                        dataTestId: dataTestId,
                        className: className,
                        value: value,
                        isSelect: isSelect,
                        isCheckbox: isCheckbox,
                        isRadio: isRadio,
                        top: rect.top,
                        inputMode: (el.inputMode || '').toLowerCase(),
                        maxLength: el.maxLength > 0 ? el.maxLength : null,
                        pattern: el.pattern || '',
                    });
                }
                return results;
            }"""

            # ─── Scoring inteligente: classifica cada campo ───
            def classify_field(field_info: dict) -> tuple:
                """Retorna (tipo, confiança) baseado em TODOS os sinais do campo."""
                # Combina todos os sinais em um texto para matching
                signals = ' '.join([
                    field_info['name'], field_info['id'], field_info['placeholder'],
                    field_info['autocomplete'], field_info['ariaLabel'],
                    field_info['labelText'], field_info['nearbyText'],
                    field_info['dataTestId'], field_info['className'],
                    field_info.get('inputMode', ''), field_info.get('pattern', ''),
                ]).lower()

                inp_type = field_info['type']
                maxlen = field_info.get('maxLength')

                # === REGRAS DE CLASSIFICAÇÃO (ordem de especificidade) ===

                # EMAIL — type=email é 100% confiável
                if inp_type == 'email':
                    return ('email', 100)
                if any(k in signals for k in ['email', 'e-mail', 'e_mail', '@']):
                    return ('email', 90)

                # TELEFONE — type=tel é 100% confiável
                if inp_type == 'tel':
                    return ('phone', 100)
                if any(k in signals for k in ['phone', 'telefone', 'celular', 'whatsapp', 'mobile', 'tel ', 'ddd']):
                    return ('phone', 90)
                if any(k in signals for k in ['(11)', '(21)', '(67)', '(xx)']):
                    return ('phone', 80)

                # CPF — muito específico
                if any(k in signals for k in ['cpf', 'cpfcnpj', 'taxid', 'tax_id', 'tax-id']):
                    return ('cpf', 95)
                if '000.000.000' in signals or '000000000' in signals:
                    return ('cpf', 90)
                if 'document' in signals and not any(k in signals for k in ['upload', 'file', 'attach']):
                    return ('cpf', 70)

                # CEP — muito específico  
                if any(k in signals for k in ['cep', 'zipcode', 'zip_code', 'zip-code', 'postal_code', 'postalcode', 'postal-code']):
                    return ('cep', 95)
                if '00000-000' in signals or '00000000' in signals:
                    return ('cep', 90)
                if maxlen and maxlen <= 9 and '00000' in signals:
                    return ('cep', 85)

                # NÚMERO (endereço) — cuidado para não confundir com outros números
                if any(k in signals for k in ['addressnumber', 'address_number', 'address-number']):
                    return ('numero', 95)
                addr_ctx = any(k in signals for k in ['endere', 'address', 'entrega', 'delivery', 'shipping'])
                if any(k in signals for k in ['numero', 'número', 'nº']) and addr_ctx:
                    return ('numero', 90)
                if 'number' in field_info['name'] and addr_ctx:
                    return ('numero', 85)
                if any(k in signals for k in ['numero', 'número', 'nº']):
                    return ('numero', 75)
                if field_info['placeholder'] in ['123', 'nº', 'n°']:
                    return ('numero', 80)

                # COMPLEMENTO
                if any(k in signals for k in ['complemento', 'complement', 'comp ']):
                    return ('complemento', 90)
                if any(k in signals for k in ['apto', 'apartamento', 'bloco', 'opcional']):
                    if addr_ctx or any(k in signals for k in ['numero', 'número', 'cep']):
                        return ('complemento', 75)

                # RUA / LOGRADOURO
                if any(k in signals for k in ['logradouro', 'street', 'address_line', 'address-line', 'addressline']):
                    return ('rua', 90)
                if 'rua' in signals and addr_ctx:
                    return ('rua', 85)
                if 'address' in field_info['name'] and 'number' not in field_info['name']:
                    return ('rua', 70)
                if 'endereco' in signals or 'endereço' in signals:
                    if not any(k in signals for k in ['cep', 'numero', 'número', 'bairro', 'cidade']):
                        return ('rua', 65)

                # BAIRRO
                if any(k in signals for k in ['bairro', 'neighborhood', 'district', 'borough']):
                    return ('bairro', 90)

                # CIDADE — cuidado para não confundir com campo "nome" que tem placeholder com nome de pessoa
                if any(k in signals for k in ['cidade', 'city', 'municipio', 'município']):
                    # Se o label ou id diz "nome" ou "name", NÃO é cidade
                    if any(k in field_info['labelText'] for k in ['nome', 'name']) or field_info['id'] in ('name', 'nome'):
                        pass  # Vai cair no scoring de nome abaixo
                    else:
                        return ('cidade', 90)

                # ESTADO (select dropdown geralmente)
                if any(k in signals for k in ['estado', 'state', 'uf ', ' uf']):
                    return ('estado', 90)
                if field_info['isSelect'] and any(k in signals for k in ['uf', 'state']):
                    return ('estado', 85)

                # NOME — PRIORIDADE ALTA: label/id "nome"/"name" SEMPRE é nome, nunca cidade
                if field_info['id'] in ('name', 'nome') or field_info['name'] in ('name', 'nome'):
                    return ('name', 98)
                if any(k in field_info['labelText'] for k in ['nome completo', 'nome', 'full name', 'name']):
                    return ('name', 95)
                if any(k in signals for k in ['full_name', 'fullname', 'customer_name', 'nome completo', 'full name']):
                    return ('name', 95)
                if field_info['autocomplete'] in ['name', 'given-name', 'family-name', 'cc-name']:
                    return ('name', 90)
                # Placeholder com padrão de nome próprio: "ex: mariana cardoso", "ex: joão silva"
                pl = field_info['placeholder'].lower()
                if any(k in pl for k in ['ex:', 'exemplo:', 'nome', 'name']):
                    # Se o placeholder contém "ex:" seguido de texto (padrão Zedy)
                    return ('name', 92)
                if 'nome' in signals and not any(k in signals for k in ['sobre', 'last', 'user']):
                    return ('name', 80)
                # Zedy e outros: placeholder ou label com "nome", "seu nome", "name"
                if any(k in signals for k in ['seu nome', 'your name', 'nome e sobrenome', 'first name']):
                    return ('name', 85)
                # Campo text genérico no topo da página que não é nenhum outro tipo
                if inp_type == 'text' and field_info.get('top', 999) < 400:
                    lb = field_info['labelText'].lower()
                    if any(k in pl for k in ['nome', 'name']) or any(k in lb for k in ['nome', 'name']):
                        return ('name', 75)

                return ('unknown', 0)

            # ─── Dados para cada tipo de campo ───
            FIELD_VALUES = {
                'name': user_data["name"],
                'email': user_data["email"],
                'phone': user_data["phone"],
                'cpf': cpf_digits,
                'cep': addr["cep"],
                'numero': addr["numero"],
                'complemento': addr.get("complemento", ""),
                'rua': addr["rua"],
                'bairro': addr["bairro"],
                'cidade': addr["cidade"],
                'estado': addr["estado"],
            }

            FIELD_LABELS = {
                'name': 'Nome', 'email': 'Email', 'phone': 'Celular',
                'cpf': 'CPF', 'cep': 'CEP', 'numero': 'Numero',
                'complemento': 'Complemento', 'rua': 'Rua',
                'bairro': 'Bairro', 'cidade': 'Cidade', 'estado': 'Estado',
            }

            SKIP_IF_FILLED = {'rua', 'bairro', 'cidade', 'estado'}
            OPTIONAL_FIELDS = {'complemento'}
            POST_FILL_DELAY = {'cep': 5.0}  # campos que precisam de delay após preenchimento (CEP → auto-complete endereço)

            async def wait_for_address_expansion_after_cep(filled: dict) -> dict:
                """Após preencher CEP, aguarda a expansão dos campos de endereço e preenche-os."""
                if 'cep' not in filled:
                    return filled
                
                session.add_log("  🏠 CEP preenchido — aguardando expansão de endereço...", "info")
                
                # Aguarda até 8s para campos de endereço aparecerem
                for attempt in range(8):
                    await asyncio.sleep(1.0)
                    try:
                        new_fields = await page.evaluate(EXTRACT_FIELDS_JS)
                        if not new_fields:
                            continue
                        
                        # Verifica se apareceram campos de endereço
                        addr_types_found = set()
                        for f in new_fields:
                            ftype, fscore = classify_field(f)
                            if ftype in ('rua', 'numero', 'bairro', 'complemento', 'cidade', 'estado') and fscore >= 60:
                                addr_types_found.add(ftype)
                        
                        if len(addr_types_found) >= 2:
                            session.add_log(f"  ✅ Campos de endereço expandidos: {list(addr_types_found)}", "success")
                            
                            # Preenche os novos campos
                            used_types = set(filled.keys())
                            classified_new = []
                            for f in new_fields:
                                ftype, fconf = classify_field(f)
                                if ftype in addr_types_found and ftype not in used_types and fconf >= 60:
                                    classified_new.append((f, ftype, fconf))
                            
                            classified_new.sort(key=lambda x: -x[2])
                            for field_info, field_type, confidence in classified_new:
                                if field_type in used_types:
                                    continue
                                value = FIELD_VALUES.get(field_type, "")
                                if not value and field_type in OPTIONAL_FIELDS:
                                    continue
                                if not value:
                                    continue
                                
                                current_val = (field_info['value'] or "").strip()
                                mask_chars_set = set("0.-_()/ ")
                                has_val = current_val and len(current_val) > 1 and not all(c in mask_chars_set for c in current_val)
                                
                                if has_val and field_type in SKIP_IF_FILLED:
                                    label = FIELD_LABELS.get(field_type, field_type)
                                    session.add_log(f"  {label}: auto-preenchido = '{current_val[:25]}'", "info")
                                    filled[field_type] = True
                                    used_types.add(field_type)
                                    continue
                                
                                if has_val:
                                    filled[field_type] = True
                                    used_types.add(field_type)
                                    continue
                                
                                # Selects (estado)
                                if field_info['isSelect'] and field_type == 'estado':
                                    try:
                                        sel = page.locator(f'[data-phantom-idx="{field_info["idx"]}"]').first
                                        await sel.select_option(value=value)
                                        session.add_log(f"  Estado: {value} (select)", "info")
                                        filled[field_type] = True
                                        used_types.add(field_type)
                                    except Exception:
                                        try:
                                            await sel.select_option(label=value)
                                            filled[field_type] = True
                                            used_types.add(field_type)
                                        except Exception:
                                            pass
                                    continue
                                
                                # Preencher campo
                                try:
                                    el = page.locator(f'[data-phantom-idx="{field_info["idx"]}"]').first
                                    if not await el.is_visible(timeout=500):
                                        continue
                                    await el.click()
                                    await asyncio.sleep(random.uniform(0.05, 0.15))
                                    await el.fill("")
                                    await asyncio.sleep(random.uniform(0.03, 0.08))
                                    await el.fill(value)
                                    await asyncio.sleep(random.uniform(0.1, 0.25))
                                    label = FIELD_LABELS.get(field_type, field_type)
                                    session.add_log(f"  {label}: {value[:25]} (score:{confidence})", "info")
                                    filled[field_type] = True
                                    used_types.add(field_type)
                                except Exception as e:
                                    session.add_log(f"  Erro preenchendo {field_type}: {str(e)[:40]}", "error")
                            
                            return filled
                    except Exception as e:
                        session.add_log(f"  Erro checando expansão: {str(e)[:40]}", "error")
                
                session.add_log("  ⚠️ Campos de endereço não expandiram após CEP", "info")
                return filled

            async def intelligent_scan_and_fill() -> dict:
                """Extrai contexto DOM completo via JS e preenche com scoring inteligente."""
                filled = {}
                mask_chars = set("0.-_()/ ")

                try:
                    fields = await page.evaluate(EXTRACT_FIELDS_JS)
                except Exception as e:
                    session.add_log(f"  Erro ao extrair campos: {str(e)[:50]}", "error")
                    return filled

                if not fields:
                    return filled

                # DEBUG: mostra todos os campos raw detectados
                for f in fields[:15]:
                    ftype, fscore = classify_field(f)
                    session.add_log(
                        f"  🔎 [{ftype}:{fscore}] name={f['name'][:20]} id={f['id'][:20]} "
                        f"ph={f['placeholder'][:20]} label={f['labelText'][:25]} "
                        f"type={f['type']} top={int(f.get('top', 0))}",
                        "info"
                    )

                # Classifica todos os campos
                classified = []
                for f in fields:
                    field_type, confidence = classify_field(f)
                    if field_type != 'unknown' and confidence >= 60:
                        classified.append((f, field_type, confidence))

                # Ordena por confiança (maior primeiro) e deduplica tipos
                classified.sort(key=lambda x: -x[2])
                used_types = set()

                for field_info, field_type, confidence in classified:
                    if field_type in used_types:
                        continue

                    value = FIELD_VALUES.get(field_type, "")
                    if not value and field_type in OPTIONAL_FIELDS:
                        continue
                    if not value:
                        continue

                    # Verifica valor atual
                    current_val = (field_info['value'] or "").strip()
                    has_value = current_val and len(current_val) > 1 and not all(c in mask_chars for c in current_val)

                    if has_value and field_type in SKIP_IF_FILLED:
                        label = FIELD_LABELS.get(field_type, field_type)
                        session.add_log(f"  {label}: ja preenchido = '{current_val[:25]}'", "info")
                        filled[field_type] = True
                        used_types.add(field_type)
                        continue

                    if has_value:
                        filled[field_type] = True
                        used_types.add(field_type)
                        continue

                    # Selects (estado) — tratamento especial
                    if field_info['isSelect'] and field_type == 'estado':
                        try:
                            sel = page.locator(f'[data-phantom-idx="{field_info["idx"]}"]').first
                            await sel.select_option(value=value)
                            session.add_log(f"  Estado: {value} (select)", "info")
                            filled[field_type] = True
                            used_types.add(field_type)
                        except Exception:
                            try:
                                await sel.select_option(label=value)
                                filled[field_type] = True
                                used_types.add(field_type)
                            except Exception:
                                pass
                        continue

                    # PREENCHE via Playwright (garante eventos React/Vue/Angular)
                    try:
                        el = page.locator(f'[data-phantom-idx="{field_info["idx"]}"]').first
                        if not await el.is_visible(timeout=500):
                            continue

                        await el.click()
                        await asyncio.sleep(random.uniform(0.05, 0.15))
                        await el.fill("")
                        await asyncio.sleep(random.uniform(0.03, 0.08))
                        await el.fill(value)
                        await asyncio.sleep(random.uniform(0.1, 0.25))

                        label = FIELD_LABELS.get(field_type, field_type)
                        display = value[:25] + ("..." if len(value) > 25 else "")
                        session.add_log(f"  {label}: {display} (score:{confidence})", "info")
                        filled[field_type] = True
                        used_types.add(field_type)

                        # Delay pós-preenchimento (CEP → auto-complete)
                        if field_type in POST_FILL_DELAY:
                            session.add_log(f"  Aguardando auto-preenchimento ({label})...", "info")
                            await asyncio.sleep(POST_FILL_DELAY[field_type])

                    except Exception as e:
                        session.add_log(f"  Erro {FIELD_LABELS.get(field_type, field_type)}: {str(e)[:40]}", "error")

                return filled

            async def handle_interactive_elements() -> bool:
                """Lida com todos os elementos interativos: radios, selects, pais, PIX, frete."""
                did_something = False

                # País Brasil
                try:
                    if await smart_select_country_brazil(page, session):
                        did_something = True
                except Exception:
                    pass

                # Estado dropdown
                try:
                    if await select_state_dropdown(page, addr["estado"], session):
                        did_something = True
                except Exception:
                    pass

                # Frete
                try:
                    if await select_shipping_option(page, session):
                        did_something = True
                except Exception:
                    pass

                # PIX
                try:
                    if await select_pix_payment(page, session):
                        did_something = True
                except Exception:
                    pass

                return did_something

            async def handle_popups_and_modals():
                """Fecha popups, modais de cookie, upsells que bloqueiam o fluxo."""
                close_selectors = [
                    'button[aria-label="Close"]', 'button[aria-label="Fechar"]',
                    '.close-modal', '.modal-close', '[data-dismiss="modal"]',
                    'button:has-text("Fechar")', 'button:has-text("×")',
                    'button:has-text("Não, obrigado")', 'button:has-text("Não quero")',
                    'button:has-text("Recusar")', 'button:has-text("Pular")',
                    # Cookie banners
                    'button:has-text("Aceitar")', 'button:has-text("Aceito")',
                    'button:has-text("Accept")', 'button:has-text("OK")',
                    '#cookie-accept', '.cookie-accept', '[data-action="accept-cookies"]',
                ]
                for sel in close_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=300):
                            await el.click()
                            session.add_log(f"  Popup/modal fechado: {sel[:40]}", "info")
                            await asyncio.sleep(0.5)
                    except Exception:
                        continue

            # ─── Helpers de Detecção de Transição v6.0 ───

            async def get_dom_fingerprint() -> dict:
                """Captura fingerprint do DOM atual para detectar transições de etapa."""
                try:
                    return await page.evaluate("""() => {
                        const inputs = document.querySelectorAll('input:not([type=hidden]), select, textarea');
                        const visibleInputs = [];
                        for (const el of inputs) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight + 200) {
                                visibleInputs.push({
                                    tag: el.tagName,
                                    name: el.name || '',
                                    type: el.type || '',
                                    placeholder: el.placeholder || '',
                                    id: el.id || '',
                                });
                            }
                        }
                        const buttons = document.querySelectorAll('button, a[role=button], input[type=submit]');
                        const visibleBtns = [];
                        for (const btn of buttons) {
                            const rect = btn.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                visibleBtns.push((btn.textContent || '').trim().substring(0, 40));
                            }
                        }
                        // Detect step indicators
                        const stepIndicators = document.querySelectorAll('[class*="step"], [class*="etapa"], [class*="stage"], [data-step], [aria-current="step"]');
                        let currentStep = '';
                        for (const s of stepIndicators) {
                            const cls = s.className || '';
                            const text = (s.textContent || '').trim().substring(0, 50);
                            if (cls.includes('active') || cls.includes('current') || s.getAttribute('aria-current')) {
                                currentStep = text;
                                break;
                            }
                        }
                        // Also check h1/h2/h3 for step titles
                        const headings = [];
                        for (const h of document.querySelectorAll('h1, h2, h3')) {
                            const rect = h.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                headings.push((h.textContent || '').trim().substring(0, 60));
                            }
                        }
                        return {
                            inputCount: visibleInputs.length,
                            inputNames: visibleInputs.map(i => i.name || i.id || i.placeholder).filter(Boolean),
                            buttonTexts: visibleBtns.filter(Boolean),
                            currentStep: currentStep,
                            headings: headings,
                            url: window.location.href,
                        };
                    }""")
                except Exception:
                    return {"inputCount": 0, "inputNames": [], "buttonTexts": [], "currentStep": "", "headings": [], "url": ""}

            def dom_changed(before: dict, after: dict) -> bool:
                """Detecta se houve transição real de etapa (novos campos, headings diferentes)."""
                if before["url"] != after["url"]:
                    return True
                if set(before["inputNames"]) != set(after["inputNames"]):
                    return True
                if before["currentStep"] and after["currentStep"] and before["currentStep"] != after["currentStep"]:
                    return True
                if before["headings"] != after["headings"]:
                    return True
                if abs(before["inputCount"] - after["inputCount"]) >= 2:
                    return True
                return False

            async def wait_for_step_transition(pre_click_fp: dict, max_wait: float = 8.0) -> bool:
                """Aguarda até que o DOM mude (nova etapa) ou timeout."""
                start = time.time()
                checks = 0
                while time.time() - start < max_wait:
                    await asyncio.sleep(0.8)
                    checks += 1
                    post_fp = await get_dom_fingerprint()
                    if dom_changed(pre_click_fp, post_fp):
                        new_fields = set(post_fp["inputNames"]) - set(pre_click_fp["inputNames"])
                        removed_fields = set(pre_click_fp["inputNames"]) - set(post_fp["inputNames"])
                        session.add_log(f"  ✅ Transição detectada! Novos campos: {list(new_fields)[:5]}", "success")
                        if removed_fields:
                            session.add_log(f"     Campos removidos: {list(removed_fields)[:5]}", "info")
                        if post_fp["currentStep"]:
                            session.add_log(f"     Etapa atual: {post_fp['currentStep'][:50]}", "info")
                        if post_fp["headings"] != pre_click_fp["headings"]:
                            session.add_log(f"     Titulo: {post_fp['headings'][:2]}", "info")
                        return True
                session.add_log(f"  ⏳ Sem transição após {max_wait}s ({checks} checks)", "info")
                return False

            # ─── Loop Adaptativo Principal v6.0 ───
            max_loops = 22
            last_url = page.url
            stale_count = 0
            step_number = 1
            consecutive_same_fields = 0
            last_field_set = set()

            for loop_num in range(1, max_loops + 1):
                session.add_log(f"═══ SCAN {loop_num}/{max_loops} (Etapa {step_number}) ═══", "info")

                # 0. Verificar sucesso
                if await check_success(page, session):
                    session.add_log("VENDA GERADA com sucesso!", "success")
                    session.successes += 1
                    return True

                # 1. Fechar popups/modais que bloqueiam
                await handle_popups_and_modals()

                # 2. Capturar fingerprint ANTES do scan
                pre_scan_fp = await get_dom_fingerprint()

                # 3. Scan inteligente DOM + preenchimento
                filled = await intelligent_scan_and_fill()
                
                # 3.5 Se preencheu CEP, aguarda expansão de endereço e preenche
                filled = await wait_for_address_expansion_after_cep(filled)
                
                filled_count = len(filled)
                current_field_set = set(filled.keys()) if filled else set()

                if filled:
                    session.add_log(f"  Campos: {list(filled.keys())}", "info")

                # Detectar se estamos vendo os mesmos campos repetidamente
                if current_field_set and current_field_set == last_field_set:
                    consecutive_same_fields += 1
                else:
                    consecutive_same_fields = 0
                last_field_set = current_field_set

                # 4. Elementos interativos (radios, selects, PIX, frete)
                radios_done = await handle_interactive_elements()

                # 5. Pausa humana
                await asyncio.sleep(random.uniform(0.3, 0.8))

                # 6. Decidir se deve clicar botão
                # Só clica se: preencheu algo OU interagiu com elementos OU está preso nos mesmos campos
                should_click = bool(filled) or radios_done or consecutive_same_fields >= 2

                clicked = False
                if should_click:
                    # Capturar fingerprint ANTES do clique para detectar transição
                    pre_click_fp = await get_dom_fingerprint()
                    clicked = await universal_click_button(page, session, loop_num)

                    if clicked:
                        # 7. AGUARDAR TRANSIÇÃO DE ETAPA (principal melhoria)
                        transitioned = await wait_for_step_transition(pre_click_fp)

                        if transitioned:
                            step_number += 1
                            consecutive_same_fields = 0
                            last_field_set = set()
                            # Espera extra para campos React/RSC renderizarem
                            await asyncio.sleep(random.uniform(1.0, 2.0))
                            # Verificar sucesso imediato pós-transição
                            if await check_success(page, session):
                                session.add_log("VENDA GERADA com sucesso!", "success")
                                session.successes += 1
                                return True
                            # Continua para próximo scan imediatamente
                            continue
                        else:
                            # Não houve transição — pode ser validação falhando
                            session.add_log("  ⚠️ Clicou mas não avançou — possível erro de validação", "info")
                            # Tenta ler mensagens de erro na página
                            try:
                                errors = await page.evaluate("""() => {
                                    const errEls = document.querySelectorAll('[class*="error"], [class*="invalid"], [role="alert"], .text-red-500, .text-destructive');
                                    const msgs = [];
                                    for (const el of errEls) {
                                        const t = (el.textContent || '').trim();
                                        if (t && t.length > 3 && t.length < 200) msgs.push(t);
                                    }
                                    return msgs.slice(0, 3);
                                }""")
                                if errors:
                                    session.add_log(f"  ❌ Erros na página: {errors}", "error")
                            except Exception:
                                pass
                            await asyncio.sleep(random.uniform(1.5, 2.5))

                # 8. Detecção de progresso
                any_action = bool(filled) or radios_done or clicked
                if not any_action:
                    stale_count += 1
                    session.add_log(f"  Sem acao possivel (stale #{stale_count})", "info")
                    if stale_count >= 6:
                        session.add_log("  Sem progresso. Encerrando.", "error")
                        break
                    # Scroll down para revelar campos escondidos
                    if stale_count >= 2:
                        try:
                            await page.evaluate("window.scrollBy(0, 300)")
                            session.add_log("  📜 Scroll para revelar campos...", "info")
                        except Exception:
                            pass
                    await asyncio.sleep(2.0)
                    continue
                else:
                    stale_count = 0

                # 9. Detectar mudança de URL (para SPAs que mudam URL entre etapas)
                current_url = page.url
                if current_url != last_url:
                    session.add_log(f"  Navegou: {current_url[:80]}", "info")
                    last_url = current_url
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        await asyncio.sleep(2.0)

                # 10. Verificar sucesso pós-ação
                if await check_success(page, session):
                    session.add_log("VENDA GERADA com sucesso!", "success")
                    session.successes += 1
                    return True

                # 11. Aguardar entre scans (menor se não clicou)
                if not clicked:
                    await asyncio.sleep(random.uniform(0.5, 1.5))

            # ═══ FIM DO LOOP ═══
            session.add_log("Verificacao final...", "info")
            await asyncio.sleep(3.0)
            if await check_success(page, session):
                session.successes += 1
                return True

            session.add_log(f"Fluxo nao concluido apos {max_loops} scans.", "error")
            session.failures += 1
            return False

        except Exception as e:
            error_msg = str(e)[:200]
            session.add_log(f"Erro: {error_msg}", "error")
            session.failures += 1
            return False
        finally:
            try:
                if context:
                    await context.close()
            except Exception:
                pass
            try:
                if browser and browser.is_connected():
                    await browser.close()
            except Exception:
                pass
            session.add_log("Sessao encerrada.", "info")


# ═══════════════════════════════════════════════════════════════════════════════
# ZEDY DIRECT API ENGINE — Checkout via Server Actions (sem navegador)
# ═══════════════════════════════════════════════════════════════════════════════

ZEDY_CHECKOUT_URL_PATTERN = re.compile(r'https?://seguro\.[^/]+/checkout/([A-Z0-9-]+)/?', re.IGNORECASE)

async def resolve_zedy_token_from_html(checkout_url: str, proxy: str = "") -> dict:
    """
    GET na página de checkout Zedy, extrai dados hidratados do RSC/Next.js.
    Retorna: token, storeId, checkoutId, produto, gateways, actionIds.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    proxy_url = proxy.strip() if proxy else None
    proxies = proxy_url if proxy_url else None
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=30, proxy=proxies) as client:
        resp = await client.get(checkout_url, headers=headers)
        html = resp.text
    
    result = {
        "token": "", "storeId": 0, "checkoutId": 0,
        "product": {}, "store": {}, "payment": {}, "shipping": {},
        "actionIds": [], "cookies": dict(resp.cookies),
    }
    
    # Extrai __NEXT_DATA__ (SSR)
    next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', html)
    if next_data_match:
        try:
            data = json.loads(next_data_match.group(1))
            props = data.get("props", {}).get("pageProps", {})
            checkout = props.get("checkout", {})
            products = checkout.get("products", [{}])
            product = products[0] if products else {}
            
            result["token"] = props.get("token", checkout.get("token", ""))
            result["storeId"] = checkout.get("storeId", props.get("storeId", 0))
            result["checkoutId"] = checkout.get("id", 0)
            result["product"] = {
                "title": product.get("title", ""),
                "productId": product.get("productId", 0),
                "variantId": product.get("variantId", product.get("shopifyProductId", 0)),
                "price": product.get("priceRaw", product.get("price", 0)),
                "quantity": product.get("quantity", 1),
                "imageUrl": product.get("image", ""),
            }
            result["store"] = {
                "name": props.get("store", {}).get("name", ""),
                "slug": props.get("store", {}).get("slug", ""),
            }
            result["payment"] = {
                "gateways": props.get("payment", {}).get("gateways", []),
                "pixDiscount": props.get("payment", {}).get("pixDiscount", 0),
            }
            result["shipping"] = {
                "requiresZipcode": bool(checkout.get("isZipcode")),
            }
            return result
        except Exception:
            pass
    
    # Fallback: parse RSC chunks (self.__next_f.push)
    rsc_chunks = []
    for m in re.finditer(r'self\.__next_f\.push\(\[[\d,]*"((?:[^"\\]|\\.)*)"\]\)', html):
        chunk = m.group(1).replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
        rsc_chunks.append(chunk)
    
    full_payload = ''.join(rsc_chunks)
    
    token_m = re.search(r'"token"\s*:\s*"(Z-[A-Z0-9]+)"', full_payload, re.IGNORECASE)
    store_id_m = re.search(r'"storeId"\s*:\s*(\d+)', full_payload)
    checkout_id_m = re.search(r'"checkout"\s*:\s*\{[^}]*"id"\s*:\s*(\d+)', full_payload)
    title_m = re.search(r'"title"\s*:\s*"([^"]+)"', full_payload)
    product_id_m = re.search(r'"productId"\s*:\s*(\d+)', full_payload)
    variant_id_m = re.search(r'"variantId"\s*:\s*(\d+)', full_payload) or re.search(r'"shopifyProductId"\s*:\s*(\d+)', full_payload)
    price_m = re.search(r'"priceRaw"\s*:\s*([\d.]+)', full_payload) or re.search(r'"price"\s*:\s*([\d.]+)', full_payload)
    image_m = re.search(r'"image"\s*:\s*"(https?://[^"]+)"', full_payload)
    quantity_m = re.search(r'"quantity"\s*:\s*(\d+)', full_payload)
    zipcode_m = re.search(r'"isZipcode"\s*:\s*(true|false)', full_payload)
    store_name_m = re.search(r'"storeName"\s*:\s*"([^"]+)"', full_payload) or re.search(r'"name"\s*:\s*"([^"]+)"', full_payload)
    store_slug_m = re.search(r'"slug"\s*:\s*"([^"]+)"', full_payload)
    pix_discount_m = re.search(r'"pixDiscount"\s*:\s*([\d.]+)', full_payload)
    gateway_m = re.search(r'"gateways?"\s*:\s*\[([^\]]*)\]', full_payload)
    
    result["token"] = token_m.group(1) if token_m else ""
    result["storeId"] = int(store_id_m.group(1)) if store_id_m else 0
    result["checkoutId"] = int(checkout_id_m.group(1)) if checkout_id_m else 0
    result["product"] = {
        "title": title_m.group(1) if title_m else "",
        "productId": int(product_id_m.group(1)) if product_id_m else 0,
        "variantId": int(variant_id_m.group(1)) if variant_id_m else 0,
        "price": float(price_m.group(1)) if price_m else 0,
        "quantity": int(quantity_m.group(1)) if quantity_m else 1,
        "imageUrl": image_m.group(1) if image_m else "",
    }
    result["store"] = {
        "name": store_name_m.group(1) if store_name_m else "",
        "slug": store_slug_m.group(1) if store_slug_m else "",
    }
    gateways = []
    if gateway_m:
        gateways = [g.strip('"') for g in re.findall(r'"([^"]+)"', gateway_m.group(1))]
    result["payment"] = {
        "gateways": gateways,
        "pixDiscount": float(pix_discount_m.group(1)) if pix_discount_m else 0,
    }
    result["shipping"] = {
        "requiresZipcode": zipcode_m.group(1) == "true" if zipcode_m else False,
    }
    
    # Extrai action IDs dos chunks de JS (next-action headers)
    action_ids = re.findall(r'"([a-f0-9]{40})"', html)
    result["actionIds"] = list(set(action_ids))[:10]
    
    return result


async def run_zedy_direct_api_session(session: EngineSession, proxy: str, user_data: dict) -> bool:
    """
    Executa checkout Zedy via Server Actions HTTP diretas — sem navegador.
    Fluxo: GET token → POST init → POST dados pessoais → POST CEP → POST pagamento
    """
    config = session.payload.direct_api_config
    if not config:
        session.add_log("Configuração de API Direta ausente!", "error")
        return False
    
    checkout_url = session.payload.target_url
    token = config.token
    
    session.add_log(f"🔗 Modo API Direta — Token: {token[:15]}...", "info")
    
    try:
        # PASSO 1: Resolver token (GET página + extrair dados hidratados)
        session.add_log("📡 Resolvendo token via GET...", "info")
        resolved = await resolve_zedy_token_from_html(checkout_url, proxy)
        
        store_id = config.store_id or resolved["storeId"]
        checkout_id = config.checkout_id or resolved["checkoutId"]
        
        if not store_id or not checkout_id:
            session.add_log(f"❌ Não conseguiu resolver token: storeId={store_id} checkoutId={checkout_id}", "error")
            return False
        
        session.add_log(f"✅ Resolvido: storeId={store_id} checkoutId={checkout_id}", "success")
        session.add_log(f"   Produto: {resolved['product'].get('title', 'N/A')[:40]} — R${resolved['product'].get('price', 0)}", "info")
        
        # Cookies e headers base para Server Actions
        cookies = resolved.get("cookies", {})
        action_ids = resolved.get("actionIds", [])
        
        base_headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
            "Accept": "text/x-component",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": re.match(r'(https?://[^/]+)', checkout_url).group(1),
            "Referer": checkout_url,
            "Next-Router-State-Tree": "",
        }
        
        proxy_url = proxy.strip() if proxy else None
        
        addr = get_random_address()
        cpf_digits = user_data["cpf"].replace(".", "").replace("-", "").replace(" ", "")
        
        async with httpx.AsyncClient(follow_redirects=True, timeout=30, proxy=proxy_url, cookies=cookies) as client:
            
            # PASSO 2: Server Action — submeter dados pessoais
            session.add_log("📤 Enviando dados pessoais...", "info")
            personal_payload = json.dumps([
                store_id, checkout_id,
                {
                    "email": user_data["email"],
                    "name": user_data["name"],
                    "phone": user_data["phone"],
                }
            ])
            
            headers_sa = {**base_headers}
            if action_ids:
                headers_sa["Next-Action"] = action_ids[0]
            
            resp1 = await client.post(checkout_url, content=personal_payload, headers=headers_sa)
            session.add_log(f"   Resposta dados pessoais: {resp1.status_code}", "info" if resp1.status_code == 200 else "error")
            
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # PASSO 3: Server Action — submeter CEP e endereço
            if resolved["shipping"].get("requiresZipcode") or config.zipcode:
                session.add_log("📤 Enviando CEP e endereço...", "info")
                zipcode = config.zipcode or addr["cep"]
                
                address_payload = json.dumps([
                    store_id, checkout_id,
                    {
                        "zipcode": zipcode,
                        "address": addr["rua"],
                        "number": addr["numero"],
                        "complement": addr.get("complemento", ""),
                        "neighborhood": addr["bairro"],
                        "city": addr["cidade"],
                        "state": addr["estado"],
                        "cpf": cpf_digits,
                    }
                ])
                
                headers_sa2 = {**base_headers}
                if len(action_ids) > 1:
                    headers_sa2["Next-Action"] = action_ids[1]
                
                resp2 = await client.post(checkout_url, content=address_payload, headers=headers_sa2)
                session.add_log(f"   Resposta endereço: {resp2.status_code}", "info" if resp2.status_code == 200 else "error")
                
                await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # PASSO 4: Server Action — selecionar frete (primeira opção)
            session.add_log("📤 Selecionando frete...", "info")
            shipping_payload = json.dumps([
                store_id, checkout_id,
                {"shippingMethodId": "0"}  # primeira opção
            ])
            
            headers_sa3 = {**base_headers}
            if len(action_ids) > 2:
                headers_sa3["Next-Action"] = action_ids[2]
            
            resp3 = await client.post(checkout_url, content=shipping_payload, headers=headers_sa3)
            session.add_log(f"   Resposta frete: {resp3.status_code}", "info" if resp3.status_code == 200 else "error")
            
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # PASSO 5: Server Action — finalizar com pagamento
            payment_method = config.payment_method or "pix"
            session.add_log(f"📤 Finalizando pedido com {payment_method.upper()}...", "info")
            
            payment_payload = json.dumps([
                store_id, checkout_id,
                {
                    "paymentMethod": payment_method,
                    "cpf": cpf_digits,
                }
            ])
            
            headers_sa4 = {**base_headers}
            if len(action_ids) > 3:
                headers_sa4["Next-Action"] = action_ids[3]
            
            resp4 = await client.post(checkout_url, content=payment_payload, headers=headers_sa4)
            resp4_text = resp4.text[:500]
            session.add_log(f"   Resposta pagamento: {resp4.status_code}", "info" if resp4.status_code == 200 else "error")
            
            # Verificar sucesso
            success_indicators = ["pix", "qr", "pedido", "sucesso", "gerado", "pagamento", "obrigado", "aguardando"]
            if any(ind in resp4_text.lower() for ind in success_indicators):
                session.add_log("🎯 VENDA GERADA VIA API DIRETA!", "success")
                session.successes += 1
                return True
            elif resp4.status_code == 200:
                session.add_log(f"   Resposta (preview): {resp4_text[:200]}", "info")
                # Status 200 pode ser sucesso mesmo sem indicador textual
                session.add_log("✅ Checkout completado (status 200)", "success")
                session.successes += 1
                return True
            else:
                session.add_log(f"❌ Falha: {resp4_text[:200]}", "error")
                session.failures += 1
                return False
                
    except Exception as e:
        session.add_log(f"❌ Erro API Direta: {str(e)[:200]}", "error")
        session.failures += 1
        return False


# ─── Loop Principal da Engine ────────────────────────────────────────────────

async def engine_loop(session: EngineSession):
    """Loop que roda em background enquanto a sessao estiver ativa."""
    payload = session.payload

    cpf_list = payload.cpfs if payload.cpfs else load_cpfs_from_file()
    if not cpf_list:
        session.add_log("Nenhum CPF disponivel! Usando CPF generico.", "error")
        cpf_list = ["00000000000"]

    proxy_list = payload.proxies if payload.proxies else [""]
    proxy_idx = 0
    successes_on_current_proxy = 0
    use_proxies = bool(payload.proxies)

    is_direct_api = payload.engine_mode == "direct_api"
    mode_label = "API DIRETA" if is_direct_api else ("LOCAL (Chromium)" if (ENGINE_MODE == "local" or not BROWSERLESS_API_KEY) else "BROWSERLESS")
    proxy_label = f"{len(payload.proxies)} proxies" if use_proxies else "SEM PROXY (IP direto)"
    session.add_log(
        f"Engine iniciada | {len(cpf_list)} CPFs | "
        f"Intervalo: {payload.interval_seconds}s | Modo: {mode_label} | {proxy_label}",
        "info",
    )
    if use_proxies:
        session.add_log(f"Rotacao de proxy a cada {payload.rotate_after_successes} sucesso(s)", "info")

    while not session._stop_event.is_set():
        proxy = proxy_list[proxy_idx]
        user_data = get_random_user_data(cpf_list)
        session.total_attempts += 1

        session.add_log(
            f"── Tentativa #{session.total_attempts} | Proxy {proxy_idx + 1}/{len(proxy_list)} ──",
            "info",
        )
        session.add_log(f"  Dados: {user_data['name']} | {user_data['email']} | CPF: {user_data['cpf'][:6]}...", "info")

        if is_direct_api:
            success = await run_zedy_direct_api_session(session, proxy, user_data)
        else:
            success = await run_checkout_session(session, proxy, user_data)

        if success:
            successes_on_current_proxy += 1
            if successes_on_current_proxy >= payload.rotate_after_successes:
                proxy_idx = (proxy_idx + 1) % len(proxy_list)
                successes_on_current_proxy = 0
                session.add_log(f"Proxy rotacionado -> #{proxy_idx + 1}", "info")
        else:
            proxy_idx = (proxy_idx + 1) % len(proxy_list)
            successes_on_current_proxy = 0
            session.add_log(f"Erro, proxy rotacionado -> #{proxy_idx + 1}", "info")

        session.add_log(f"Aguardando {payload.interval_seconds}s...", "info")

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
    mode = "local" if (ENGINE_MODE == "local" or not BROWSERLESS_API_KEY) else "browserless"
    return {
        "status": "ok",
        "engine": "PHANTOM ENGINE v7.0 UNIVERSAL",
        "mode": mode,
        "sessions": len(sessions),
        "features": ["browser", "direct_api", "zedy_token_resolver"],
    }


class ResolveTokenPayload(BaseModel):
    token: str

@app.post("/api/zedy/resolve-token")
async def api_resolve_zedy_token(payload: ResolveTokenPayload, _=Depends(verify_token)):
    """Resolve um token Zedy: GET na página, extrai storeId, checkoutId, produto, gateways."""
    token = payload.token.strip()
    if not re.match(r'^Z-[A-Z0-9]+$', token, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Token Zedy inválido")
    
    # Constroi URL a partir do token (usa domínio genérico — o redirect resolve)
    # Tenta primeiro com o padrão seguro.*.com
    checkout_url = f"https://seguro.texanostoreoficial.com/checkout/{token}"
    
    try:
        resolved = await resolve_zedy_token_from_html(checkout_url)
        if not resolved.get("storeId") and not resolved.get("checkoutId"):
            raise HTTPException(status_code=404, detail="Token não resolveu nenhum dado")
        
        return {
            "token": resolved.get("token", token),
            "storeId": resolved.get("storeId", 0),
            "checkoutId": resolved.get("checkoutId", 0),
            "product": resolved.get("product", {}),
            "store": resolved.get("store", {}),
            "payment": resolved.get("payment", {}),
            "shipping": resolved.get("shipping", {}),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao resolver token: {str(e)[:200]}")

# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = "LOCAL (Chromium)" if (ENGINE_MODE == "local" or not BROWSERLESS_API_KEY) else "BROWSERLESS"
    log.info(f"Iniciando PHANTOM ENGINE v4.0 — Modo: {mode}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
