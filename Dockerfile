############################
# Builder
############################
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Copy dependency metadata only
COPY pyproject.toml ./

# Create virtualenv and install deps
RUN uv venv /opt/venv \
    && . /opt/venv/bin/activate \
    && uv pip install --upgrade pip \
    && uv pip install --no-cache-dir .

############################
# Runtime (prod)
############################
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy code (prod only)
COPY src/celine ./celine
COPY config ./config
COPY ontologies ./ontologies
COPY migrations ./migrations
COPY pyproject.toml ./
COPY README.md ./

USER appuser
EXPOSE 8000

CMD ["uvicorn", "celine.dt.main:create_app", "--host", "0.0.0.0", "--port", "8000"]

############################
# Dev (compose target)
############################
FROM runtime AS dev

# In dev we rely on bind mounts, so DO NOT copy code again
# Keep same entrypoint but enable reload via compose command

ENV APP_ENV=dev
ENV LOG_LEVEL=DEBUG
