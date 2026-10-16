# ============================================================
# Stage 1: builder — install Poetry and export requirements
# ============================================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.2 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

WORKDIR /build

COPY pyproject.toml poetry.lock* ./

RUN poetry export \
        --without-hashes \
        --without dev \
        --format requirements.txt \
        --output requirements.txt

# ============================================================
# Stage 2: runtime
# ============================================================
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# System dependencies: gcc for C extensions, libpq-dev for psycopg2,
# chromium + deps for Playwright headless rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        libffi-dev \
        libssl-dev \
        # Playwright / Chromium runtime deps
        chromium \
        chromium-driver \
        libnss3 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgtk-3-0 \
        # Utilities
        wget \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from the builder stage export
COPY --from=builder /build/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Install Playwright and its Chromium browser bundle
RUN pip install --no-cache-dir playwright \
    && playwright install chromium \
    && playwright install-deps chromium

# Create non-root user
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy application source
COPY --chown=appuser:appgroup . .

# Storage directory for generated reports / uploads
RUN mkdir -p /app/storage && chown -R appuser:appgroup /app/storage

USER appuser

EXPOSE 8000

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
