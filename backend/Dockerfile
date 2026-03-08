FROM python:3.11-slim

WORKDIR /app

# Copia arquivos do backend
COPY phantom_engine_v3_api.py .
COPY cpfs.txt* ./

# Instala dependencias Python (Playwright apenas como client, sem Chrome local)
RUN pip install --no-cache-dir fastapi uvicorn pydantic playwright \
    && playwright install-deps \
    && playwright install chromium

EXPOSE 8000

CMD ["python", "phantom_engine_v3_api.py"]
