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
COPY infra/entrypoint-api.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

EXPOSE 8000
CMD ["/entrypoint.sh"]
