FROM python:3.11-slim

WORKDIR /app

# Build context = raiz do monorepo
COPY apps/api/requirements.txt /tmp/req-api.txt
COPY packages/shared /opt/packages/shared
RUN pip install --no-cache-dir -e /opt/packages/shared \
 && grep -v '^-e ' /tmp/req-api.txt > /tmp/req-api-noedit.txt \
 && pip install --no-cache-dir -r /tmp/req-api-noedit.txt

COPY apps/api/app /app/app
COPY apps/api/alembic /app/alembic
COPY apps/api/alembic.ini /app/alembic.ini

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
