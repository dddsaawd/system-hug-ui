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
# Modo: "local" usa Chromium instalado no servidor, "browserless" usa chrome remoto
ENGINE_MODE = os.environ.get("ENGINE_MODE", "local")  # "local" ou "browserless"
BROWSERLESS_API_KEY = os.environ.get("BROWSERLESS_API_KEY", "")
BROWSERLESS_BASE_URL = f"wss://chrome.browserless.io?token={BROWSERLESS_API_KEY}&timeout=30000"

CPF_FILE = Path("cpfs.txt")

# ─── App FastAPI ──────────────────────────────────────────────────────────────
app = FastAPI(title="PHANTOM ENGINE v3.9 UNIVERSAL", version="3.9.0")

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
            if await field.is_visible(timeout=1500):
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
            if await field.is_visible(timeout=1500):
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
    Busca em button, a, div, span — por texto parcial (case-insensitive).
    """
    # Textos de botao ordenados por prioridade (mais especificos primeiro)
    button_texts = [
        # Finalizacao / Pagamento
        "Gerar Pix", "Gerar pix", "GERAR PIX", "Gerar PIX",
        "Finalizar compra", "FINALIZAR COMPRA", "Finalizar Compra",
        "Finalizar pedido", "FINALIZAR PEDIDO", "Finalizar Pedido",
        "Finalizar", "FINALIZAR",
        "Comprar agora", "COMPRAR AGORA", "Comprar Agora",
        "Comprar", "COMPRAR",
        "Pagar agora", "PAGAR AGORA", "Pagar",
        "Concluir compra", "CONCLUIR COMPRA",
        "Concluir", "CONCLUIR",
        "Confirmar pedido", "CONFIRMAR PEDIDO",
        "Confirmar", "CONFIRMAR",
        "Realizar pagamento", "REALIZAR PAGAMENTO",
        "Efetuar pagamento", "EFETUAR PAGAMENTO",
        "Fechar pedido", "FECHAR PEDIDO",
        "Gerar Boleto", "GERAR BOLETO",
        "Place Order", "Submit",
        # Navegacao entre etapas
        "Ir para Pagamento", "IR PARA PAGAMENTO", "Ir para pagamento",
        "Ir para o pagamento", "IR PARA O PAGAMENTO",
        "Ir para entrega", "IR PARA ENTREGA", "Ir para Entrega",
        "Escolher frete", "ESCOLHER FRETE", "Escolher Frete",
        "Salvar e continuar", "SALVAR E CONTINUAR",
        "Prosseguir", "PROSSEGUIR",
        # Genericos
        "Continuar", "CONTINUAR", "Continue",
        "Avançar", "AVANÇAR", "Avancar", "AVANCAR",
        "Próximo", "PRÓXIMO", "Proximo", "PROXIMO",
        "Next", "NEXT",
    ]

    # Estrategia 1: Busca por texto exato em button
    for text in button_texts:
        try:
            btn = page.locator(f'button:has-text("{text}")').first
            if await btn.is_visible(timeout=800):
                await btn.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await btn.click(timeout=5000)
                session.add_log(f"  Botao <button> '{text}' clicado!", "success")
                return True
        except Exception:
            continue

    # Estrategia 2: Busca em <a> (links estilizados como botao)
    for text in button_texts:
        try:
            link = page.locator(f'a:has-text("{text}")').first
            if await link.is_visible(timeout=800):
                await link.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await link.click(timeout=5000)
                session.add_log(f"  Botao <a> '{text}' clicado!", "success")
                return True
        except Exception:
            continue

    # Estrategia 3: Busca em qualquer elemento clicavel (div, span) com role=button
    for text in button_texts:
        try:
            el = page.locator(f'[role="button"]:has-text("{text}")').first
            if await el.is_visible(timeout=800):
                await el.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await el.click(timeout=5000)
                session.add_log(f"  Botao [role=button] '{text}' clicado!", "success")
                return True
        except Exception:
            continue

    # Estrategia 4: Busca por getByRole('button')
    for text in button_texts:
        try:
            btn = page.get_by_role("button", name=text, exact=False).first
            if await btn.is_visible(timeout=800):
                await btn.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await btn.click(timeout=5000)
                session.add_log(f"  Botao (role) '{text}' clicado!", "success")
                return True
        except Exception:
            continue

    # Estrategia 5: Busca por getByText em qualquer elemento
    for text in button_texts[:20]:  # Apenas os mais especificos
        try:
            el = page.get_by_text(text, exact=False).first
            if await el.is_visible(timeout=800):
                tag = await el.evaluate("el => el.tagName")
                if tag and tag.upper() in ("BUTTON", "A", "DIV", "SPAN", "INPUT"):
                    await el.scroll_into_view_if_needed()
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                    await el.click(timeout=5000)
                    session.add_log(f"  Botao (text) <{tag}> '{text}' clicado!", "success")
                    return True
        except Exception:
            continue

    # Estrategia 6: Fallback - qualquer button[type=submit] visivel
    try:
        submit_btns = page.locator('button[type="submit"]')
        count = await submit_btns.count()
        for i in range(count):
            btn = submit_btns.nth(i)
            if await btn.is_visible(timeout=1000):
                btn_text = (await btn.text_content() or "").strip()
                if btn_text and "voltar" not in btn_text.lower() and "back" not in btn_text.lower():
                    await btn.scroll_into_view_if_needed()
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                    await btn.click(timeout=5000)
                    session.add_log(f"  Botao submit '{btn_text[:40]}' clicado!", "success")
                    return True
    except Exception:
        pass

    # Estrategia 7: Fallback - qualquer button visivel que nao seja "Voltar"
    try:
        all_btns = page.locator("button")
        count = await all_btns.count()
        for i in range(count):
            btn = all_btns.nth(i)
            if await btn.is_visible(timeout=800):
                btn_text = (await btn.text_content() or "").strip()
                if btn_text and len(btn_text) > 2:
                    lower = btn_text.lower()
                    skip_words = ["voltar", "back", "cancelar", "fechar", "close", "x"]
                    if not any(w in lower for w in skip_words):
                        await btn.scroll_into_view_if_needed()
                        await asyncio.sleep(random.uniform(0.1, 0.3))
                        await btn.click(timeout=5000)
                        session.add_log(f"  Botao fallback '{btn_text[:40]}' clicado!", "success")
                        return True
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
    frete_selectors = [
        # Radio buttons de frete
        'label:has-text("Frete")', 'label:has-text("frete")',
        'label:has-text("Envio")', 'label:has-text("envio")',
        'label:has-text("Entrega")',
        'label:has-text("JADLOG")', 'label:has-text("Correios")',
        'label:has-text("PAC")', 'label:has-text("SEDEX")',
        'label:has-text("Grátis")', 'label:has-text("Gratis")',
        # Divs clicaveis
        'div:has-text("Frete Grátis")', 'div:has-text("Frete grátis")',
        'div:has-text("Frete Gratis")',
        # Inputs de radio
        'input[name="shipping"]', 'input[name="frete"]',
        'input[name="shipping_method"]', 'input[name="delivery"]',
        # Generico - qualquer radio dentro de secao de frete
        '[class*="shipping"] input[type="radio"]',
        '[class*="frete"] input[type="radio"]',
        '[class*="delivery"] input[type="radio"]',
    ]
    for sel in frete_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1500):
                await el.click()
                frete_text = (await el.text_content() or "frete")[:50]
                session.add_log(f"  Frete selecionado: {frete_text}", "success")
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

                if "@" in proxy_clean:
                    auth_part, server_part = proxy_clean.split("@")
                    username, password = auth_part.split(":")
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
                    "--single-process",
                ]
                browser = await p.chromium.launch(
                    headless=True,
                    args=launch_args,
                    proxy=proxy_config
                )
                session.add_log("Chromium local iniciado!", "success")
            else:
                # === MODO BROWSERLESS ===
                session.add_log("Conectando ao Browserless.io...", "info")
                ws_url = BROWSERLESS_BASE_URL
                session.add_log(f"Timeout Browserless: 30000ms", "info")
                browser = await p.chromium.connect_over_cdp(ws_url)
                session.add_log("Browserless conectado!", "success")

            context = await browser.new_context(
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

            # Navega para o checkout
            session.add_log(f"Navegando: {session.payload.target_url}", "info")
            await page.goto(session.payload.target_url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(random.uniform(1.5, 2.5))

            addr = get_random_address()
            cpf_digits = user_data["cpf"].replace(".", "").replace("-", "").replace(" ", "")

            # ═══════════════════════════════════════════════════════════
            # LOOP DE ETAPAS — ate 6 etapas
            # ═══════════════════════════════════════════════════════════

            max_etapas = 6
            campos_ja_preenchidos = set()  # Evita preencher o mesmo campo 2x

            for etapa in range(1, max_etapas + 1):
                session.add_log(f"═══ ETAPA {etapa} ═══", "info")
                await asyncio.sleep(random.uniform(0.3, 0.7))

                campos_nesta_etapa = 0

                # --- NOME ---
                if "nome" not in campos_ja_preenchidos:
                    nome_selectors = [
                        'input[name="name"]', 'input[name="nome"]', 'input#name',
                        'input[name="customer_name"]', 'input[name="full_name"]',
                        'input[name="fullName"]', 'input[name="customerName"]',
                        'input[placeholder*="Nome"]', 'input[placeholder*="nome"]',
                        'input[placeholder*="Maria"]', 'input[placeholder*="completo"]',
                        'input[autocomplete="name"]', 'input[autocomplete="given-name"]',
                    ]
                    filled = await smart_fill_field(page, nome_selectors, user_data["name"], "Nome", session)
                    if not filled:
                        filled = await smart_fill_field_by_label(page, ["Nome completo", "Nome", "Seu nome"], user_data["name"], "Nome", session)
                    if filled:
                        campos_ja_preenchidos.add("nome")
                        campos_nesta_etapa += 1

                # --- EMAIL ---
                if "email" not in campos_ja_preenchidos:
                    email_selectors = [
                        'input[name="email"]', 'input[name="e-mail"]', 'input#email',
                        'input[name="customer_email"]', 'input[name="customerEmail"]',
                        'input[type="email"]',
                        'input[placeholder*="email"]', 'input[placeholder*="Email"]',
                        'input[placeholder*="e-mail"]', 'input[placeholder*="@"]',
                        'input[autocomplete="email"]',
                    ]
                    filled = await smart_fill_field(page, email_selectors, user_data["email"], "Email", session)
                    if not filled:
                        filled = await smart_fill_field_by_label(page, ["E-mail", "Email", "Seu e-mail"], user_data["email"], "Email", session)
                    if filled:
                        campos_ja_preenchidos.add("email")
                        campos_nesta_etapa += 1

                # --- PAIS (+55) ---
                if "pais" not in campos_ja_preenchidos:
                    if await smart_select_country_brazil(page, session):
                        campos_ja_preenchidos.add("pais")

                # --- TELEFONE ---
                if "phone" not in campos_ja_preenchidos:
                    phone_selectors = [
                        'input[name="phone"]', 'input[name="telefone"]', 'input#phone',
                        'input[name="celular"]', 'input[name="cellphone"]',
                        'input[name="customer_phone"]', 'input[name="whatsapp"]',
                        'input[type="tel"]',
                        'input[placeholder*="celular"]', 'input[placeholder*="Celular"]',
                        'input[placeholder*="telefone"]', 'input[placeholder*="Telefone"]',
                        'input[placeholder*="WhatsApp"]', 'input[placeholder*="Whatsapp"]',
                        'input[placeholder*="(11)"]', 'input[placeholder*="99999"]',
                        'input[placeholder*="DDD"]',
                        'input[autocomplete="tel"]',
                    ]
                    filled = await smart_fill_field(page, phone_selectors, user_data["phone"], "Celular", session)
                    if not filled:
                        filled = await smart_fill_field_by_label(page, ["Celular", "Telefone", "WhatsApp", "Celular/WhatsApp", "Celular/Whatsapp"], user_data["phone"], "Celular", session)
                    if filled:
                        campos_ja_preenchidos.add("phone")
                        campos_nesta_etapa += 1

                # --- CPF (pode aparecer em QUALQUER etapa) ---
                if "cpf" not in campos_ja_preenchidos:
                    cpf_selectors = [
                        'input[name="cpf"]', 'input[name="document"]', 'input#cpf',
                        'input[name="doc"]', 'input[name="customer_cpf"]',
                        'input[name="cpfCnpj"]', 'input[name="taxId"]',
                        'input[name="cpf_cnpj"]', 'input[name="documentNumber"]',
                        'input[placeholder*="CPF"]', 'input[placeholder*="cpf"]',
                        'input[placeholder*="000.000.000"]', 'input[placeholder*="documento"]',
                        'input[placeholder*="Documento"]',
                    ]
                    filled = await smart_fill_field(page, cpf_selectors, cpf_digits, "CPF", session)
                    if not filled:
                        filled = await smart_fill_field_by_label(page, ["CPF", "CPF/CNPJ", "CPF/CNPJ do pagador", "Documento", "CPF ou CNPJ"], cpf_digits, "CPF", session)
                    if filled:
                        campos_ja_preenchidos.add("cpf")
                        campos_nesta_etapa += 1

                # --- CEP ---
                if "cep" not in campos_ja_preenchidos:
                    cep_selectors = [
                        'input[name="cep"]', 'input[name="zipcode"]', 'input#cep',
                        'input[name="zip_code"]', 'input[name="postalCode"]',
                        'input[name="postal_code"]', 'input[name="zip"]',
                        'input[placeholder*="CEP"]', 'input[placeholder*="cep"]',
                        'input[placeholder*="00000-000"]', 'input[placeholder*="00000000"]',
                        'input[autocomplete="postal-code"]',
                    ]
                    filled = await smart_fill_field(page, cep_selectors, addr["cep"], "CEP", session)
                    if not filled:
                        filled = await smart_fill_field_by_label(page, ["CEP", "Código Postal", "Codigo Postal"], addr["cep"], "CEP", session)
                    if filled:
                        campos_ja_preenchidos.add("cep")
                        campos_nesta_etapa += 1
                        # Espera auto-preenchimento do CEP
                        session.add_log("  Aguardando auto-preenchimento do CEP...", "info")
                        await asyncio.sleep(random.uniform(2.0, 3.5))

                # --- RUA ---
                if "rua" not in campos_ja_preenchidos:
                    rua_selectors = [
                        'input[name="street"]', 'input[name="rua"]', 'input#street',
                        'input[name="address"]', 'input[name="endereco"]',
                        'input[name="address_street"]', 'input[name="logradouro"]',
                        'input[placeholder*="Rua"]', 'input[placeholder*="rua"]',
                        'input[placeholder*="Avenida"]', 'input[placeholder*="endereco"]',
                        'input[placeholder*="Endereço"]', 'input[placeholder*="logradouro"]',
                    ]
                    filled = await smart_fill_field(page, rua_selectors, addr["rua"], "Rua", session)
                    if not filled:
                        filled = await smart_fill_field_by_label(page, ["Rua", "Endereço", "Endereço/Rua", "Logradouro"], addr["rua"], "Rua", session)
                    if filled:
                        campos_ja_preenchidos.add("rua")
                        campos_nesta_etapa += 1

                # --- NUMERO ---
                if "numero" not in campos_ja_preenchidos:
                    numero_selectors = [
                        'input[name="number"]', 'input[name="numero"]', 'input#number',
                        'input[name="addressNumber"]', 'input[name="address_number"]',
                        'input[name="num"]',
                        'input[placeholder*="123"]', 'input[placeholder*="mero"]',
                        'input[placeholder*="Número"]', 'input[placeholder*="numero"]',
                        'input[placeholder*="Nº"]',
                    ]
                    filled = await smart_fill_field(page, numero_selectors, addr["numero"], "Numero", session)
                    if not filled:
                        filled = await smart_fill_field_by_label(page, ["Número", "Numero", "Nº"], addr["numero"], "Numero", session)
                    if filled:
                        campos_ja_preenchidos.add("numero")
                        campos_nesta_etapa += 1

                # --- COMPLEMENTO ---
                if "complemento" not in campos_ja_preenchidos and addr["complemento"]:
                    comp_selectors = [
                        'input[name="complement"]', 'input[name="complemento"]', 'input#complement',
                        'input[name="address_complement"]', 'input[name="comp"]',
                        'input[placeholder*="Apto"]', 'input[placeholder*="Bloco"]',
                        'input[placeholder*="complemento"]', 'input[placeholder*="Complemento"]',
                        'input[placeholder*="Opcional"]',
                    ]
                    filled = await smart_fill_field(page, comp_selectors, addr["complemento"], "Complemento", session)
                    if not filled:
                        filled = await smart_fill_field_by_label(page, ["Complemento", "Complemento (Opcional)"], addr["complemento"], "Complemento", session)
                    if filled:
                        campos_ja_preenchidos.add("complemento")
                        campos_nesta_etapa += 1

                # --- BAIRRO ---
                if "bairro" not in campos_ja_preenchidos:
                    bairro_selectors = [
                        'input[name="neighborhood"]', 'input[name="bairro"]', 'input#neighborhood',
                        'input[name="district"]', 'input[name="address_neighborhood"]',
                        'input[placeholder*="bairro"]', 'input[placeholder*="Bairro"]',
                        'input[placeholder*="Seu bairro"]',
                    ]
                    filled = await smart_fill_field(page, bairro_selectors, addr["bairro"], "Bairro", session)
                    if not filled:
                        filled = await smart_fill_field_by_label(page, ["Bairro", "Seu bairro"], addr["bairro"], "Bairro", session)
                    if filled:
                        campos_ja_preenchidos.add("bairro")
                        campos_nesta_etapa += 1

                # --- CIDADE ---
                if "cidade" not in campos_ja_preenchidos:
                    cidade_selectors = [
                        'input[name="city"]', 'input[name="cidade"]', 'input#city',
                        'input[name="address_city"]',
                        'input[placeholder*="cidade"]', 'input[placeholder*="Cidade"]',
                        'input[placeholder*="Sua cidade"]',
                    ]
                    filled = await smart_fill_field(page, cidade_selectors, addr["cidade"], "Cidade", session)
                    if not filled:
                        filled = await smart_fill_field_by_label(page, ["Cidade", "Sua cidade"], addr["cidade"], "Cidade", session)
                    if filled:
                        campos_ja_preenchidos.add("cidade")
                        campos_nesta_etapa += 1

                # --- ESTADO ---
                if "estado" not in campos_ja_preenchidos:
                    # Tenta input primeiro
                    estado_selectors = [
                        'input[name="state"]', 'input[name="estado"]', 'input#state',
                        'input[name="uf"]', 'input[name="address_state"]',
                        'input[placeholder*="UF"]', 'input[placeholder*="Estado"]',
                        'input[placeholder*="estado"]',
                    ]
                    filled = await smart_fill_field(page, estado_selectors, addr["estado"], "Estado", session)
                    if not filled:
                        filled = await smart_fill_field_by_label(page, ["Estado", "UF"], addr["estado"], "Estado", session)
                    if not filled:
                        # Tenta dropdown <select>
                        filled = await select_state_dropdown(page, addr["estado"], session)
                    if filled:
                        campos_ja_preenchidos.add("estado")
                        campos_nesta_etapa += 1

                # --- SELECIONAR FRETE (se opcoes de frete estiverem visiveis) ---
                frete_selecionado = await select_shipping_option(page, session)

                # --- SELECIONAR PIX (se estiver na tela de pagamento) ---
                pix_selecionado = await select_pix_payment(page, session)

                session.add_log(f"  Etapa {etapa}: {campos_nesta_etapa} campos preenchidos nesta etapa", "info")
                await asyncio.sleep(random.uniform(0.3, 0.6))

                # --- VERIFICA SUCESSO ANTES DE CLICAR BOTAO ---
                if await check_success(page, session):
                    session.successes += 1
                    return True

                # --- CLICAR NO BOTAO ---
                url_antes = page.url
                botao_clicado = await universal_click_button(page, session, etapa)

                if not botao_clicado:
                    # Se nao achou botao e nao preencheu campos, pode ser tela final
                    if campos_nesta_etapa == 0:
                        session.add_log(f"  Nenhum botao e nenhum campo na etapa {etapa}. Verificando sucesso...", "info")
                        await asyncio.sleep(1.0)
                        if await check_success(page, session):
                            session.successes += 1
                            return True
                        break
                    else:
                        # Preencheu campos mas nao achou botao — tenta scroll e retry
                        session.add_log("  Tentando scroll para encontrar botao...", "info")
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(1.0)
                        botao_clicado = await universal_click_button(page, session, etapa)
                        if not botao_clicado:
                            session.add_log("  Botao nao encontrado mesmo apos scroll.", "error")
                            break

                # --- ESPERA TRANSICAO ENTRE ETAPAS ---
                session.add_log("  Aguardando proxima etapa...", "info")
                await asyncio.sleep(random.uniform(1.5, 3.0))

                # Verifica se a URL mudou (indica transicao de etapa)
                url_depois = page.url
                if url_antes != url_depois:
                    session.add_log(f"  URL mudou: ...{url_depois[-40:]}", "info")

                # Verifica sucesso apos transicao
                if await check_success(page, session):
                    session.successes += 1
                    return True

            # ═══ FIM DO LOOP DE ETAPAS ═══
            # Ultima verificacao de sucesso
            session.add_log("Fluxo completo. Verificacao final...", "info")
            await asyncio.sleep(2.0)
            if await check_success(page, session):
                session.successes += 1
                return True

            session.add_log("Fluxo percorrido mas venda nao confirmada.", "error")
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

    proxy_list = payload.proxies
    proxy_idx = 0
    successes_on_current_proxy = 0

    mode_label = "LOCAL (Chromium)" if (ENGINE_MODE == "local" or not BROWSERLESS_API_KEY) else "BROWSERLESS"
    session.add_log(
        f"Engine iniciada | {len(cpf_list)} CPFs | "
        f"Intervalo: {payload.interval_seconds}s | Modo: {mode_label}",
        "info",
    )
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
    log.info("Iniciando PHANTOM ENGINE v3.5 — Universal Checkout Engine")
    log.info(f"Browserless: {BROWSERLESS_BASE_URL[:50]}...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
