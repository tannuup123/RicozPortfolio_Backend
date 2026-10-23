# ---------- Stage 1: Builder ----------
FROM python:3.11-slim AS builder
WORKDIR /build
# Copy packaging configuration and application source so setuptools can build
# and install dependencies directly from pyproject.toml without hardcoding.
COPY pyproject.toml ./
COPY app/ ./app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .
# ---------- Stage 2: Runtime ----------
FROM python:3.11-slim
WORKDIR /app
# Copy installed packages and executables from builder.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
# Copy application code and Alembic migrations.
COPY . .
EXPOSE 8000
# Entrypoint: run migrations then start uvicorn.
# Uses Render's $PORT env var with a fallback of 8000 (architecture.md §10).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
