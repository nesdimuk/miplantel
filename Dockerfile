FROM python:3.12-slim

WORKDIR /srv/miplantel

# Dependencias primero para aprovechar la cache de capas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts ./scripts

EXPOSE 8000

# Migraciones al arrancar y luego el servidor (idempotente: upgrade head no hace nada si ya está al día)
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
