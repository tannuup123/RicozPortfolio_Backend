# ---------- Stage 1: Builder ----------
FROM python:3.11-slim AS builder

WORKDIR /build

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# ---------- Stage 2: Runtime ----------
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code.
COPY . .

EXPOSE 8000

# Entrypoint: run migrations then start uvicorn (architecture.md §10).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
