# syntax=docker/dockerfile:1

# ---- Build stage ----
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime stage ----
FROM python:3.11-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app && adduser --system --ingroup app app

COPY --from=builder /install /usr/local

ARG PREDOWNLOAD_BASE_MODEL=false
RUN if [ "$PREDOWNLOAD_BASE_MODEL" = "true" ]; then \
        python -c "from transformers import AutoModelForCausalLM, AutoTokenizer; \
        AutoModelForCausalLM.from_pretrained('TinyLlama/TinyLlama-1.1B-Chat-v1.0'); \
        AutoTokenizer.from_pretrained('TinyLlama/TinyLlama-1.1B-Chat-v1.0')"; \
    fi

COPY app/ ./app/
COPY scripts/ ./scripts/
COPY pyproject.toml ./

RUN mkdir -p /app/models /app/data/models && chown -R app:app /app

USER app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

VOLUME ["/app/models"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["gunicorn", "app.main:app", \
    "--worker-class", "uvicorn.workers.UvicornWorker", \
    "--bind", "0.0.0.0:8000", \
    "--workers", "2", \
    "--timeout", "120"]
