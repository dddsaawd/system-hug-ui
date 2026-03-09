FROM python:3.11-slim

WORKDIR /app

# Instala dependencias de sistema para Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libatspi2.0-0 libxshmfence1 libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*

# Copia arquivos do backend
COPY phantom_engine_v3_api.py .
COPY cpfs.txt* ./

# Instala dependencias Python e Playwright Chromium
RUN pip install --no-cache-dir fastapi uvicorn pydantic playwright \
    && playwright install chromium

# Modo local por padrao (sem Browserless)
ENV ENGINE_MODE=local

EXPOSE 8000

CMD ["python", "phantom_engine_v3_api.py"]
