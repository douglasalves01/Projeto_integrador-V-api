FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/ai/requirements.txt /tmp/req-ai.txt
COPY packages/shared /opt/packages/shared
RUN pip install --no-cache-dir -e /opt/packages/shared \
 && grep -v '^-e ' /tmp/req-ai.txt > /tmp/req-ai-noedit.txt \
 && pip install --no-cache-dir -r /tmp/req-ai-noedit.txt

COPY apps/ai/app /app/app
COPY apps/ai/scripts /app/scripts
COPY apps/ai/models /app/models
COPY apps/ai/pyproject.toml /app/pyproject.toml

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/llm/info || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
