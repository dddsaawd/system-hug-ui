FROM python:3.11-slim

WORKDIR /app

# Instala dependencias Python
RUN pip install --no-cache-dir fastapi uvicorn pydantic playwright httpx

# Instala Chromium COMPLETO (não headless_shell) com todas as deps de sistema
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install --with-deps chromium && \
    echo "=== Playwright browsers ===" && \
    find /ms-playwright -name "chrome" -o -name "chromium" -o -name "headless_shell" 2>/dev/null | head -20 && \
    echo "=== Done ==="

# Copia arquivos do backend
COPY phantom_engine_v3_api.py .
COPY cpfs.txt* ./

ENV ENGINE_MODE=local

EXPOSE 8000

CMD ["python", "phantom_engine_v3_api.py"]
