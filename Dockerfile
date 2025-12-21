FROM python:3.12-slim AS builder

# System deps (minimal, reproducible)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv (official install method)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Copy dependency metadata only (better layer caching)
COPY pyproject.toml ./

# Resolve and install dependencies into a virtual environment
RUN uv venv /opt/venv \
    && . /opt/venv/bin/activate \
    && uv pip install --upgrade pip \
    && uv pip install --no-cache-dir .

FROM python:3.12-slim AS runtime

# Runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --uid 10001 appuser

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy application code
COPY dt ./dt
COPY ontologies ./ontologies
COPY config ./config
COPY migrations ./migrations
COPY README.md ./
COPY pyproject.toml ./

# Create data directory for SQLite / artifacts
RUN mkdir -p /data && chown -R appuser:appuser /data /dt

USER appuser

EXPOSE 8000

# Production server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
