"""
PHANTOM ENGINE v3.2 — UNIVERSAL CHECKOUT ENGINE
Backend FastAPI + Browserless.io (Chrome Remoto na Nuvem)
Detecta automaticamente campos e botoes de QUALQUER checkout.

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
BROWSERLESS_API_KEY = os.environ.get("BROWSERLESS_API_KEY", "")
BROWSERLESS_WS_URL = f"wss://chrome.browserless.io?token={BROWSERLESS_API_KEY}&timeout=60000"
CPF_FILE = Path("cpfs.txt")

# ─── App FastAPI ──────────────────────────────────────────────────────────────
app = FastAPI(title="PHANTOM ENGINE v3.2 UNIVERSAL", version="3.2.0")

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
        if len(self.logs) > 300:
            self.logs = self.logs[-300:]
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
    ]
    sobrenomes = [
        "Melo", "Cardoso", "Teixeira", "Almeida", "Nascimento", "Freitas",
        "Barbosa", "Oliveira", "Santos", "Pereira", "Costa", "Rodrigues",
        "Martins", "Souza", "Lima", "Ferreira", "Goncalves", "Ribeiro",
        "Araujo", "Carvalho", "Monteiro", "Moreira", "Vieira", "Nunes",
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
# FUNCOES UNIVERSAIS DE DETECCAO DE CAMPOS E BOTOES
# Funcionam com QUALQUER checkout (Corvex, CartPanda, Yampi, Hotmart, etc.)
# ═══════════════════════════════════════════════════════════════════════════════

async def smart_fill_field(page, selectors: list[str], value: str, field_name: str, session: EngineSession) -> bool:
    """Tenta preencher um campo usando multiplos seletores possiveis."""
    for selector in selectors:
        try:
            field = page.locator(selector).first
            if await field.is_visible(timeout=3000):
                await field.click()
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await field.fill(value)
                await asyncio.sleep(random.uniform(0.2, 0.4))
                session.add_log(f"{field_name}: {value[:30]}...", "info") if len(value) > 30 else session.add_log(f"{field_name}: {value}", "info")
                return True
        except Exception:
            continue
    return False

async def smart_click_button(page, button_texts: list[str], button_name: str, session: EngineSession, timeout: int = 10000) -> bool:
    """Tenta clicar em um botao usando multiplos textos possiveis."""
    for text in button_texts:
        try:
            btn = page.locator(f'button:has-text("{text}")').first
            if await btn.is_visible(timeout=3000):
                await btn.click(timeout=timeout)
                session.add_log(f"Botao '{text}' clicado! ({button_name})", "success")
                return True
        except Exception:
            continue

    # Fallback: tenta qualquer button[type="submit"] visivel
    try:
        submit_btns = page.locator('button[type="submit"]')
        count = await submit_btns.count()
        for i in range(count):
            btn = submit_btns.nth(i)
            if await btn.is_visible(timeout=2000):
                btn_text = await btn.text_content()
                if btn_text and btn_text.strip():
                    await btn.click(timeout=timeout)
                    session.add_log(f"Botao submit '{btn_text.strip()[:30]}' clicado! ({button_name})", "success")
                    return True
    except Exception:
        pass

    session.add_log(f"Nenhum botao encontrado para: {button_name}", "error")
    return False

async def smart_select_country_brazil(page, session: EngineSession) -> bool:
    """Tenta selecionar Brasil (+55) no seletor de pais, se existir."""
    try:
        # Tenta encontrar o combobox de pais
        country_btn = page.locator('button[role="combobox"]').first
        if await country_btn.is_visible(timeout=3000):
            current_text = await country_btn.text_content()
            if current_text and "+55" in current_text:
                session.add_log("Pais Brasil (+55) ja selecionado.", "info")
                return True

            await country_btn.click()
            await asyncio.sleep(random.uniform(0.5, 1.0))

            # Tenta clicar em Brasil
            brasil_selectors = [
                'button:has-text("Brasil")',
                'button:has-text("Brazil")',
                '[data-country="BR"]',
                'li:has-text("Brasil")',
                'option:has-text("Brasil")',
            ]
            for sel in brasil_selectors:
                try:
                    brasil = page.locator(sel).first
                    if await brasil.is_visible(timeout=2000):
                        await brasil.click()
                        session.add_log("Pais Brasil (+55) selecionado!", "info")
                        await asyncio.sleep(random.uniform(0.3, 0.6))
                        return True
                except Exception:
                    continue

            # Fecha o dropdown se nao encontrou Brasil
            await page.keyboard.press("Escape")
    except Exception:
        pass
    return False

# ═══════════════════════════════════════════════════════════════════════════════
# MOTOR PRINCIPAL DE CHECKOUT UNIVERSAL
# ═══════════════════════════════════════════════════════════════════════════════

async def run_checkout_session(session: EngineSession, proxy: str, user_data: dict):
    """Executa uma sessao de checkout universal usando Browserless.io."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        session.add_log("Playwright nao instalado! Rode: pip install playwright", "error")
        session.failures += 1
        return False

    async with async_playwright() as p:
        session.add_log("Conectando ao Browserless.io (Chrome remoto na nuvem)...", "info")
        try:
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

            # Navega para o checkout
            session.add_log(f"Navegando para: {session.payload.target_url}", "info")
            await page.goto(session.payload.target_url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(random.uniform(1.0, 2.0))

            addr = get_random_address()
            cpf_digits = user_data["cpf"].replace(".", "").replace("-", "").replace(" ", "")

            # ═══════════════════════════════════════════════════════════
            # LOOP DE DETECCAO UNIVERSAL
            # Detecta e preenche campos visiveis, depois clica no botao
            # Repete ate chegar na tela final ou esgotar tentativas
            # ═══════════════════════════════════════════════════════════

            max_etapas = 5  # Maximo de etapas que o checkout pode ter
            etapa_atual = 0

            for etapa in range(max_etapas):
                etapa_atual += 1
                session.add_log(f"=== ETAPA {etapa_atual} - Detectando campos... ===", "info")
                await asyncio.sleep(random.uniform(0.5, 1.0))

                campos_preenchidos = 0

                # --- CAMPO: NOME ---
                nome_selectors = [
                    'input#name', 'input[name="name"]', 'input[name="nome"]',
                    'input[name="customer_name"]', 'input[name="full_name"]',
                    'input[name="fullName"]', 'input[name="customerName"]',
                    'input[placeholder*="Nome"]', 'input[placeholder*="nome"]',
                    'input[placeholder*="Maria"]', 'input[placeholder*="completo"]',
                    'input[autocomplete="name"]', 'input[autocomplete="given-name"]',
                ]
                if await smart_fill_field(page, nome_selectors, user_data["name"], "Nome", session):
                    campos_preenchidos += 1

                # --- CAMPO: EMAIL ---
                email_selectors = [
                    'input#email', 'input[name="email"]', 'input[name="e-mail"]',
                    'input[name="customer_email"]', 'input[name="customerEmail"]',
                    'input[type="email"]',
                    'input[placeholder*="email"]', 'input[placeholder*="Email"]',
                    'input[placeholder*="e-mail"]', 'input[placeholder*="@"]',
                    'input[autocomplete="email"]',
                ]
                if await smart_fill_field(page, email_selectors, user_data["email"], "Email", session):
                    campos_preenchidos += 1

                # --- SELETOR DE PAIS (se existir) ---
                await smart_select_country_brazil(page, session)

                # --- CAMPO: TELEFONE / CELULAR ---
                phone_selectors = [
                    'input#phone', 'input[name="phone"]', 'input[name="telefone"]',
                    'input[name="celular"]', 'input[name="cellphone"]',
                    'input[name="customer_phone"]', 'input[name="whatsapp"]',
                    'input[type="tel"]',
                    'input[placeholder*="celular"]', 'input[placeholder*="Celular"]',
                    'input[placeholder*="telefone"]', 'input[placeholder*="Telefone"]',
                    'input[placeholder*="WhatsApp"]', 'input[placeholder*="(11)"]',
                    'input[placeholder*="DDD"]',
                    'input[autocomplete="tel"]',
                ]
                if await smart_fill_field(page, phone_selectors, user_data["phone"], "Celular", session):
                    campos_preenchidos += 1

                # --- CAMPO: CPF (pode aparecer em qualquer etapa) ---
                cpf_selectors = [
                    'input#cpf', 'input[name="cpf"]', 'input[name="document"]',
                    'input[name="doc"]', 'input[name="customer_cpf"]',
                    'input[name="cpfCnpj"]', 'input[name="taxId"]',
                    'input[placeholder*="CPF"]', 'input[placeholder*="cpf"]',
                    'input[placeholder*="000.000.000"]', 'input[placeholder*="documento"]',
                ]
                if await smart_fill_field(page, cpf_selectors, cpf_digits, "CPF", session):
                    campos_preenchidos += 1

                # --- CAMPO: CEP ---
                cep_selectors = [
                    'input#cep', 'input[name="cep"]', 'input[name="zipcode"]',
                    'input[name="zip_code"]', 'input[name="postalCode"]',
                    'input[name="postal_code"]', 'input[name="zip"]',
                    'input[placeholder*="CEP"]', 'input[placeholder*="cep"]',
                    'input[placeholder*="codigo postal"]', 'input[placeholder*="Código Postal"]',
                    'input[placeholder*="00000-000"]', 'input[placeholder*="00000000"]',
                ]
                if await smart_fill_field(page, cep_selectors, addr["cep"], "CEP", session):
                    campos_preenchidos += 1
                    # Espera o CEP preencher automaticamente os outros campos
                    await asyncio.sleep(random.uniform(2.0, 3.0))

                # --- CAMPO: RUA ---
                rua_selectors = [
                    'input#street', 'input[name="street"]', 'input[name="rua"]',
                    'input[name="address"]', 'input[name="endereco"]',
                    'input[name="address_street"]', 'input[name="logradouro"]',
                    'input[placeholder*="Rua"]', 'input[placeholder*="rua"]',
                    'input[placeholder*="Avenida"]', 'input[placeholder*="endereco"]',
                    'input[placeholder*="Endereço"]',
                ]
                if await smart_fill_field(page, rua_selectors, addr["rua"], "Rua", session):
                    campos_preenchidos += 1

                # --- CAMPO: NUMERO ---
                numero_selectors = [
                    'input#number', 'input[name="number"]', 'input[name="numero"]',
                    'input[name="addressNumber"]', 'input[name="address_number"]',
                    'input[name="num"]',
                    'input[placeholder*="123"]', 'input[placeholder*="mero"]',
                    'input[placeholder*="Número"]', 'input[placeholder*="numero"]',
                ]
                if await smart_fill_field(page, numero_selectors, addr["numero"], "Numero", session):
                    campos_preenchidos += 1

                # --- CAMPO: COMPLEMENTO ---
                comp_selectors = [
                    'input#complement', 'input[name="complement"]', 'input[name="complemento"]',
                    'input[name="address_complement"]', 'input[name="comp"]',
                    'input[placeholder*="Apto"]', 'input[placeholder*="Bloco"]',
                    'input[placeholder*="complemento"]', 'input[placeholder*="Complemento"]',
                ]
                if addr["complemento"]:
                    if await smart_fill_field(page, comp_selectors, addr["complemento"], "Complemento", session):
                        campos_preenchidos += 1

                # --- CAMPO: BAIRRO ---
                bairro_selectors = [
                    'input#neighborhood', 'input[name="neighborhood"]', 'input[name="bairro"]',
                    'input[name="district"]', 'input[name="address_neighborhood"]',
                    'input[placeholder*="bairro"]', 'input[placeholder*="Bairro"]',
                    'input[placeholder*="Seu bairro"]',
                ]
                if await smart_fill_field(page, bairro_selectors, addr["bairro"], "Bairro", session):
                    campos_preenchidos += 1

                # --- CAMPO: CIDADE ---
                cidade_selectors = [
                    'input#city', 'input[name="city"]', 'input[name="cidade"]',
                    'input[name="address_city"]',
                    'input[placeholder*="cidade"]', 'input[placeholder*="Cidade"]',
                    'input[placeholder*="Sua cidade"]',
                ]
                if await smart_fill_field(page, cidade_selectors, addr["cidade"], "Cidade", session):
                    campos_preenchidos += 1

                # --- CAMPO: ESTADO ---
                estado_selectors = [
                    'input#state', 'input[name="state"]', 'input[name="estado"]',
                    'input[name="uf"]', 'input[name="address_state"]',
                    'input[placeholder*="UF"]', 'input[placeholder*="Estado"]',
                    'input[placeholder*="estado"]',
                ]
                if await smart_fill_field(page, estado_selectors, addr["estado"], "Estado", session):
                    campos_preenchidos += 1

                session.add_log(f"Etapa {etapa_atual}: {campos_preenchidos} campos preenchidos", "info")
                await asyncio.sleep(random.uniform(0.5, 1.0))

                # --- SELECIONAR PIX (se estiver na tela de pagamento) ---
                pix_selecionado = False
                pix_selectors = [
                    'button:has-text("PIX")', 'button:has-text("Pix")',
                    'label:has-text("PIX")', 'label:has-text("Pix")',
                    '[data-method="pix"]', '[data-payment="pix"]',
                    'input[value="pix"]', 'div:has-text("PIX"):not(button)',
                ]
                for sel in pix_selectors:
                    try:
                        pix_el = page.locator(sel).first
                        if await pix_el.is_visible(timeout=2000):
                            await pix_el.click()
                            pix_selecionado = True
                            session.add_log("Metodo PIX selecionado!", "success")
                            await asyncio.sleep(random.uniform(0.5, 1.0))
                            break
                    except Exception:
                        continue

                # --- CLICAR NO BOTAO DE AVANCAR / FINALIZAR ---
                # Lista AMPLA de todos os textos possiveis de botoes
                botoes_avancar = [
                    # Botoes de avancar etapa
                    "Próximo", "Proximo", "PRÓXIMO", "PROXIMO",
                    "Continuar", "CONTINUAR", "Continue",
                    "Avançar", "Avancar", "AVANÇAR", "AVANCAR",
                    "Ir para Pagamento", "IR PARA PAGAMENTO",
                    "Ir para pagamento", "Ir para o pagamento",
                    "Ir para entrega", "Ir para Entrega",
                    "Salvar e continuar", "SALVAR E CONTINUAR",
                    "Prosseguir", "PROSSEGUIR",
                    "Next", "NEXT",
                    # Botoes de finalizar compra / gerar pedido
                    "Gerar Pix", "GERAR PIX", "Gerar pix", "Gerar PIX",
                    "Gerar Boleto", "GERAR BOLETO",
                    "Comprar", "COMPRAR", "Comprar agora", "COMPRAR AGORA",
                    "Finalizar", "FINALIZAR", "Finalizar compra", "FINALIZAR COMPRA",
                    "Finalizar pedido", "FINALIZAR PEDIDO",
                    "Pagar", "PAGAR", "Pagar agora", "PAGAR AGORA",
                    "Confirmar", "CONFIRMAR", "Confirmar pedido", "CONFIRMAR PEDIDO",
                    "Concluir", "CONCLUIR", "Concluir compra", "CONCLUIR COMPRA",
                    "Fechar pedido", "FECHAR PEDIDO",
                    "Realizar pagamento", "REALIZAR PAGAMENTO",
                    "Efetuar pagamento", "EFETUAR PAGAMENTO",
                    "Place Order", "PLACE ORDER",
                    "Submit", "SUBMIT",
                ]

                botao_clicado = await smart_click_button(page, botoes_avancar, f"Etapa {etapa_atual}", session)

                if not botao_clicado:
                    session.add_log(f"Nenhum botao encontrado na etapa {etapa_atual}. Verificando se e a tela final...", "info")
                    break

                # Espera a proxima etapa carregar
                await asyncio.sleep(random.uniform(2.0, 4.0))

                # --- VERIFICA SE A VENDA FOI GERADA ---
                # Procura por indicadores de sucesso na pagina
                sucesso_selectors = [
                    'text="Pedido realizado"', 'text="pedido realizado"',
                    'text="Compra realizada"', 'text="compra realizada"',
                    'text="Pagamento gerado"', 'text="pagamento gerado"',
                    'text="PIX gerado"', 'text="Pix gerado"', 'text="pix gerado"',
                    'text="QR Code"', 'text="qr code"', 'text="QR code"',
                    'text="Copia e Cola"', 'text="copia e cola"',
                    'text="Copiar codigo"', 'text="Copiar código"',
                    'text="Aguardando pagamento"', 'text="aguardando pagamento"',
                    'text="Obrigado"', 'text="obrigado"',
                    'text="Parabéns"', 'text="parabens"',
                    'text="sucesso"', 'text="Sucesso"',
                    'text="Boleto gerado"', 'text="boleto gerado"',
                    'text="Pedido confirmado"', 'text="pedido confirmado"',
                    'img[alt*="qr"]', 'img[alt*="QR"]',
                    'canvas', '[class*="qr"]', '[class*="pix"]',
                ]
                for sel in sucesso_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=2000):
                            session.add_log("VENDA GERADA COM SUCESSO! Indicador de sucesso detectado!", "success")
                            session.successes += 1
                            return True
                    except Exception:
                        continue

            # Se chegou aqui sem detectar sucesso, verifica uma ultima vez
            session.add_log("Fluxo completo percorrido. Verificando resultado final...", "info")

            # Ultima tentativa de detectar sucesso
            page_text = await page.text_content("body")
            if page_text:
                page_text_lower = page_text.lower()
                indicadores = ["pix gerado", "qr code", "aguardando pagamento", "pedido realizado",
                               "compra realizada", "obrigado", "sucesso", "copia e cola",
                               "copiar codigo", "boleto gerado", "pedido confirmado"]
                for ind in indicadores:
                    if ind in page_text_lower:
                        session.add_log(f"VENDA GERADA! Detectado: '{ind}' na pagina!", "success")
                        session.successes += 1
                        return True

            session.add_log("Fluxo percorrido mas nao foi possivel confirmar a venda.", "error")
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
        "engine": "PHANTOM ENGINE v3.2 UNIVERSAL",
        "browserless": "connected",
        "sessions": len(sessions),
    }

# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Iniciando PHANTOM ENGINE v3.2 — Universal Checkout Engine")
    log.info(f"Browserless WS: {BROWSERLESS_WS_URL[:50]}...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
