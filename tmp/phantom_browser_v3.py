"""
╔═════════════════════════════════════════════════════════════════════════════════╗
║   PHANTOM ENGINE v3.0 — NAVEGADOR FANTASMA                                      ║
║   Automação de Checkout com Preenchimento e Cliques Reais (Playwright)          ║
║                                                                                 ║
║   Rodar: python phantom_browser_v3.py                                           ║
╚═════════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import random
import logging
import time
from pathlib import Path
from playwright.async_api import async_playwright

# ─── Configuração de Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("phantom_browser")

# ─── Configurações Globais ────────────────────────────────────────────────────
CHECKOUT_URL = "https://seguro.texanostoreoficial.com/checkout/Z-07KZD03I0W26/"
CPF_FILE = Path("cpfs.txt")
PROXY_FILE = Path("proxies.txt") # Arquivo para a lista de proxies
INTERVALO_SEGUNDOS = 120 # 2 minutos

# ─── Helpers ──────────────────────────────────────────────────────────────────
def load_list_from_file(filepath: Path) -> list[str]:
    """Carrega uma lista de um arquivo, uma linha por item."""
    if not filepath.exists():
        log.error(f"❌ Arquivo {filepath} não encontrado! Crie o arquivo e adicione os dados.")
        return []
    with open(filepath, "r") as f:
        return [line.strip() for line in f if line.strip()]

def get_random_user_data(cpf_list: list[str]):
    nomes = ["Gabriel", "Beatriz", "Rafael", "Larissa", "Thiago", "Fernanda", "Bruno", "Camila"]
    sobrenomes = ["Melo", "Cardoso", "Teixeira", "Almeida", "Nascimento", "Freitas", "Barbosa"]
    dominios = ["@gmail.com", "@outlook.com"]
    
    nome = f"{random.choice(nomes)} {random.choice(sobrenomes)}"
    email = f"{nome.lower().replace(' ', '_')}{random.randint(10,99)}{random.choice(dominios)}"
    cpf = random.choice(cpf_list) if cpf_list else "00000000000"
    celular = f"(67) 9{random.randint(8000, 9999)}-{random.randint(1000, 9999)}"
    
    return {
        "name": nome,
        "email": email,
        "cpf": cpf,
        "phone": celular
    }

# ─── Lógica Principal de Automação (Playwright) ───────────────────────────────
async def run_checkout_session(proxy: str, user_data: dict):
    async with async_playwright() as p:
        log.info(f"🚀 Iniciando navegador com proxy: {proxy}")
        try:
            browser = await p.chromium.launch(
                headless=True, # True para rodar invisível, False para ver a tela
                proxy={"server": proxy}
            )
            context = await browser.new_context()
            page = await context.new_page()

            log.info(f"Navengando para: {CHECKOUT_URL}")
            await page.goto(CHECKOUT_URL, timeout=60000)

            # --- ETAPA 1: DADOS PESSOAIS ---
            log.info("Preenchendo dados pessoais...")
            await page.fill('input[name="name"]', user_data["name"])
            await page.fill('input[name="email"]', user_data["email"])
            await page.fill('input[name="phone"]', user_data["phone"])
            await page.click('button:has-text("CONTINUAR")')
            
            # --- ETAPA 2: ENTREGA ---
            log.info("Aguardando e preenchendo dados de entrega...")
            await page.wait_for_selector('input[name="cpf"]', timeout=15000)
            await page.fill('input[name="cpf"]', user_data["cpf"])
            # O checkout parece não pedir endereço completo, apenas CPF na segunda etapa
            await page.click('button:has-text("CONTINUAR")')

            # --- ETAPA 3: PAGAMENTO ---
            log.info("Aguardando tela de pagamento...")
            await page.wait_for_selector('text="Opção de pagamento"', timeout=15000)
            log.info("✅ Checkout alcançou a tela de pagamento com sucesso!")
            
            # Aqui você pode adicionar a lógica para selecionar PIX/Boleto e finalizar
            # Exemplo: await page.click('div:has-text("PIX")')
            
            await asyncio.sleep(5) # Aguarda um pouco para garantir que tudo foi processado

        except Exception as e:
            log.error(f"❌ Erro durante a automação: {e}")
        finally:
            if 'browser' in locals() and browser.is_connected():
                await browser.close()
            log.info("Navegador fechado.")

# ─── Loop Principal ─────────────────────────────────────────────────────────
async def main():
    log.info("Iniciando PHANTOM ENGINE v3.0 - Navegador Fantasma")
    
    cpf_list = load_list_from_file(CPF_FILE)
    proxy_list = load_list_from_file(PROXY_FILE)

    if not cpf_list or not proxy_list:
        log.error("Listas de CPF ou Proxy estão vazias. Encerrando.")
        return

    proxy_idx = 0
    while True:
        proxy = proxy_list[proxy_idx]
        user_data = get_random_user_data(cpf_list)
        
        await run_checkout_session(proxy, user_data)
        
        # Rotaciona o proxy
        proxy_idx = (proxy_idx + 1) % len(proxy_list)
        
        log.info(f"⏳ Aguardando {INTERVALO_SEGUNDOS} segundos para a próxima sessão...")
        await asyncio.sleep(INTERVALO_SEGUNDOS)

if __name__ == "__main__":
    # Instalação do Playwright (executar uma vez no terminal)
    # playwright install
    asyncio.run(main())
