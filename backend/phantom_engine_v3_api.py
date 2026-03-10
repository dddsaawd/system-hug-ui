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
import subprocess
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



class StartPayload(BaseModel):
    target_url: str
    proxies: list[str] = Field(default=[])
    interval_seconds: int = Field(default=120, ge=1, le=3600)
    cpfs: Optional[list[str]] = None
    headless: bool = True
    rotate_after_successes: int = Field(default=1, ge=1, le=100)
    is_product_url: bool = Field(default=False)  # True = navega pelo produto/carrinho antes

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

            context = await browser.new_context(
                proxy=context_proxy if context_proxy else None,
                user_agent=random.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                ]),
                viewport={"width": random.choice([1366, 1440, 1920]), "height": random.choice([768, 900, 1080])},
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
            )
            page = await context.new_page()

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
            # FLUXO DE CHECKOUT ADAPTATIVO UNIVERSAL v5.0
            # Scan de campos visiveis → preenche tudo → clica botao → repete
            # Adapta-se a QUALQUER checkout automaticamente
            # ═══════════════════════════════════════════════════════════

            # Mapa de keywords → dados (prioridade por especificidade)
            FIELD_MAP = {
                # Nome
                "name": {"keywords": ["name", "nome", "full_name", "fullname", "customer_name"], "ph_keywords": ["nome", "name"], "value": user_data["name"], "label": "Nome"},
                # Email
                "email": {"keywords": ["email", "e-mail", "e_mail"], "ph_keywords": ["email", "@", "e-mail"], "type_match": "email", "value": user_data["email"], "label": "Email"},
                # Telefone
                "phone": {"keywords": ["phone", "telefone", "celular", "whatsapp", "tel", "mobile"], "ph_keywords": ["celular", "telefone", "whatsapp", "ddd", "(11)", "(21)", "(67)"], "type_match": "tel", "value": user_data["phone"], "label": "Celular"},
                # CPF
                "cpf": {"keywords": ["cpf", "document", "doc", "cpfcnpj", "taxid", "tax_id"], "ph_keywords": ["000.000.000", "cpf", "documento"], "value": cpf_digits, "label": "CPF"},
                # CEP
                "cep": {"keywords": ["cep", "zipcode", "zip_code", "zip", "postal_code", "postalcode"], "ph_keywords": ["00000-000", "00000000", "00000", "cep"], "value": addr["cep"], "label": "CEP", "post_delay": 4.0},
                # Número
                "numero": {"keywords": ["number", "numero", "num", "addressnumber", "address_number"], "ph_keywords": ["123", "mero", "número", "numero", "nº"], "value": addr["numero"], "label": "Numero"},
                # Complemento
                "complemento": {"keywords": ["complement", "complemento", "comp"], "ph_keywords": ["apto", "complemento", "opcional", "apartamento", "bloco"], "value": addr["complemento"] or "", "label": "Complemento", "optional": True},
                # Rua
                "rua": {"keywords": ["street", "rua", "logradouro", "address", "endereco", "address_line"], "ph_keywords": ["rua", "logradouro", "endereço", "endereco", "avenida"], "value": addr["rua"], "label": "Rua", "skip_if_filled": True},
                # Bairro
                "bairro": {"keywords": ["neighborhood", "bairro", "district"], "ph_keywords": ["bairro", "distrito"], "value": addr["bairro"], "label": "Bairro", "skip_if_filled": True},
                # Cidade
                "cidade": {"keywords": ["city", "cidade", "municipio"], "ph_keywords": ["cidade", "município", "municipio"], "value": addr["cidade"], "label": "Cidade", "skip_if_filled": True},
            }

            async def scan_and_fill_fields() -> dict:
                """Escaneia TODOS os campos visiveis e preenche o que puder. Retorna resumo."""
                filled = {}
                already_filled_fields = set()
                mask_chars = set("0.-_()/ ")

                try:
                    inputs = page.locator("input:visible, textarea:visible")
                    count = await inputs.count()
                except Exception:
                    return filled

                for i in range(min(count, 20)):
                    try:
                        inp = inputs.nth(i)
                        inp_name = (await inp.get_attribute("name") or "").lower()
                        inp_ph = (await inp.get_attribute("placeholder") or "").lower()
                        inp_type = (await inp.get_attribute("type") or "").lower()
                        inp_id = (await inp.get_attribute("id") or "").lower()
                        inp_autocomplete = (await inp.get_attribute("autocomplete") or "").lower()

                        # Pula campos nao preenchíveis
                        if inp_type in ("hidden", "checkbox", "radio", "submit", "button", "file", "image"):
                            continue

                        # Verifica se ja tem valor
                        val = await inp.input_value()
                        stripped = (val or "").strip()
                        has_value = stripped and len(stripped) > 1 and not all(c in mask_chars for c in stripped)

                        # Identifica qual campo é
                        matched_field = None
                        for field_key, field_config in FIELD_MAP.items():
                            # Match por type HTML
                            if "type_match" in field_config and inp_type == field_config["type_match"]:
                                matched_field = field_key
                                break
                            # Match por autocomplete
                            if inp_autocomplete:
                                for kw in field_config["keywords"]:
                                    if kw in inp_autocomplete:
                                        matched_field = field_key
                                        break
                            if matched_field:
                                break
                            # Match por name/id
                            combined = inp_name + " " + inp_id
                            for kw in field_config["keywords"]:
                                if kw in combined:
                                    matched_field = field_key
                                    break
                            if matched_field:
                                break
                            # Match por placeholder
                            for kw in field_config.get("ph_keywords", []):
                                if kw in inp_ph:
                                    matched_field = field_key
                                    break
                            if matched_field:
                                break

                        if not matched_field:
                            continue

                        field_config = FIELD_MAP[matched_field]

                        # Ja preenchemos este tipo nesta rodada?
                        if matched_field in already_filled_fields:
                            continue

                        # Campo opcional sem valor definido?
                        if field_config.get("optional") and not field_config["value"]:
                            continue

                        # Campo ja preenchido pelo CEP (rua, bairro, cidade)?
                        if has_value and field_config.get("skip_if_filled"):
                            session.add_log(f"  {field_config['label']}: ja preenchido = '{stripped[:25]}'", "info")
                            already_filled_fields.add(matched_field)
                            filled[matched_field] = True
                            continue

                        # Ja tem valor valido? Pula
                        if has_value:
                            already_filled_fields.add(matched_field)
                            filled[matched_field] = True
                            continue

                        # PREENCHE!
                        try:
                            await inp.click()
                            await asyncio.sleep(random.uniform(0.05, 0.15))
                            await inp.fill("")
                            await asyncio.sleep(random.uniform(0.03, 0.08))
                            await inp.fill(field_config["value"])
                            await asyncio.sleep(random.uniform(0.1, 0.25))
                            display = field_config["value"][:25]
                            session.add_log(f"  {field_config['label']}: {display}", "info")
                            filled[matched_field] = True
                            already_filled_fields.add(matched_field)

                            # Delay especial (ex: CEP precisa esperar auto-preenchimento)
                            if "post_delay" in field_config:
                                session.add_log(f"  Aguardando auto-preenchimento ({field_config['label']})...", "info")
                                await asyncio.sleep(field_config["post_delay"])
                        except Exception as e:
                            session.add_log(f"  Erro ao preencher {field_config['label']}: {str(e)[:50]}", "error")

                    except Exception:
                        continue

                return filled

            async def handle_radios_and_selects() -> bool:
                """Lida com radio buttons (frete, pagamento) e dropdowns (estado, pais)."""
                did_something = False

                # Selecionar pais Brasil
                try:
                    pais = await smart_select_country_brazil(page, session)
                    if pais:
                        did_something = True
                except Exception:
                    pass

                # Selecionar estado em dropdown
                try:
                    estado = await select_state_dropdown(page, addr["estado"], session)
                    if estado:
                        did_something = True
                except Exception:
                    pass

                # Selecionar frete (se visivel)
                try:
                    frete = await select_shipping_option(page, session)
                    if frete:
                        did_something = True
                except Exception:
                    pass

                # Selecionar PIX (se visivel)
                try:
                    pix = await select_pix_payment(page, session)
                    if pix:
                        did_something = True
                except Exception:
                    pass

                return did_something

            # ─── Loop Adaptativo Principal ───
            max_loops = 15
            last_url = ""
            stale_count = 0

            for loop_num in range(1, max_loops + 1):
                session.add_log(f"═══ SCAN {loop_num}/{max_loops} ═══", "info")

                # 0. Verificar sucesso PRIMEIRO
                if await check_success(page, session):
                    session.add_log("VENDA GERADA com sucesso!", "success")
                    session.successes += 1
                    return True

                # 1. Escanear e preencher TODOS os campos visiveis
                filled = await scan_and_fill_fields()
                if filled:
                    session.add_log(f"  Campos preenchidos: {list(filled.keys())}", "info")

                # 2. Lidar com radios/selects (frete, PIX, pais, estado)
                await handle_radios_and_selects()

                # 3. Pequena pausa humana
                await asyncio.sleep(random.uniform(0.3, 0.8))

                # 4. Clicar no melhor botao disponivel
                clicked = await universal_click_button(page, session, loop_num)

                if not clicked and not filled:
                    # Nada para fazer — pagina pode estar carregando
                    stale_count += 1
                    session.add_log(f"  Nenhuma acao possivel (stale #{stale_count})", "info")
                    if stale_count >= 4:
                        session.add_log("  Muitas tentativas sem progresso. Encerrando.", "error")
                        break
                    await asyncio.sleep(2.0)
                    continue
                else:
                    stale_count = 0

                # 5. Aguardar navegacao/transicao
                await asyncio.sleep(random.uniform(2.0, 3.5))

                # 6. Detectar mudanca de URL (progresso)
                current_url = page.url
                if current_url != last_url:
                    session.add_log(f"  URL mudou: {current_url[:80]}", "info")
                    last_url = current_url
                    # Aguardar carregamento
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass

                # 7. Verificar sucesso apos acao
                if await check_success(page, session):
                    session.add_log("VENDA GERADA com sucesso!", "success")
                    session.successes += 1
                    return True

            # ═══ FIM DO LOOP ═══
            session.add_log("Fluxo completo. Verificacao final...", "info")
            await asyncio.sleep(2.0)
            if await check_success(page, session):
                session.successes += 1
                return True

            session.add_log(f"Fluxo percorrido mas venda nao confirmada apos {max_loops} scans.", "error")
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

    mode_label = "LOCAL (Chromium)" if (ENGINE_MODE == "local" or not BROWSERLESS_API_KEY) else "BROWSERLESS"
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

        success = await run_checkout_session(session, proxy, user_data)

        if success:
            successes_on_current_proxy += 1
            if successes_on_current_proxy >= payload.rotate_after_successes:
                proxy_idx = (proxy_idx + 1) % len(proxy_list)
                successes_on_current_proxy = 0
                session.add_log(f"Proxy rotacionado -> #{proxy_idx + 1}", "info")
        else:
            # Em caso de erro, rotaciona proxy tambem
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
        "engine": "PHANTOM ENGINE v4.0 LOCAL",
        "mode": mode,
        "sessions": len(sessions),
    }

# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = "LOCAL (Chromium)" if (ENGINE_MODE == "local" or not BROWSERLESS_API_KEY) else "BROWSERLESS"
    log.info(f"Iniciando PHANTOM ENGINE v4.0 — Modo: {mode}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
