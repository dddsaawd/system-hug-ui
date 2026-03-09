FROM python:3.11-slim

WORKDIR /app

# Instala dependencias Python
RUN pip install --no-cache-dir fastapi uvicorn pydantic playwright

# Instala Chromium COMPLETO com todas as deps de sistema
ENV PLAYWRIGHT_BROWSERS_PATH=0
RUN playwright install --with-deps chromium

# Copia arquivos do backend
COPY phantom_engine_v3_api.py .
COPY cpfs.txt* ./

ENV ENGINE_MODE=local

EXPOSE 8000

CMD ["python", "phantom_engine_v3_api.py"]
