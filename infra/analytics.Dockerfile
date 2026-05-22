FROM python:3.11-slim

WORKDIR /app

COPY apps/analytics/pyproject.toml /tmp/pyproject.toml
RUN pip install --no-cache-dir \
    "sqlalchemy>=2.0.25" "psycopg[binary]>=3.1.18" \
    "pandas>=2.1.0" "pyarrow>=15.0.0" "matplotlib>=3.8.0" \
    "click>=8.1.7" "pydantic-settings>=2.5.2"

COPY apps/analytics/analytics /app/analytics
RUN mkdir -p /app/reports

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
