#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# migrate.sh — run Alembic migrations to the latest revision
#
# Usage:
#   bash scripts/migrate.sh                   # upgrade to head
#   bash scripts/migrate.sh downgrade -1      # pass extra alembic args
#
# Environment variables honoured:
#   DATABASE_URL  — overrides the URL in alembic.ini (optional)
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
MIGRATIONS_DIR="${PROJECT_ROOT}/database/migrations"

# ---- validate directories --------------------------------------------------
if [ ! -d "${BACKEND_DIR}" ]; then
    echo "ERROR: backend directory not found at ${BACKEND_DIR}" >&2
    exit 1
fi

if [ ! -f "${MIGRATIONS_DIR}/alembic.ini" ]; then
    echo "ERROR: alembic.ini not found at ${MIGRATIONS_DIR}/alembic.ini" >&2
    exit 1
fi

# ---- export DATABASE_URL from .env if present ------------------------------
ENV_FILE="${PROJECT_ROOT}/config/.env"
if [ -f "${ENV_FILE}" ]; then
    # shellcheck disable=SC2046
    export $(grep -v '^#' "${ENV_FILE}" | xargs -d '\n') 2>/dev/null || true
fi

# ---- ensure the Python path includes the backend package -------------------
export PYTHONPATH="${BACKEND_DIR}:${PYTHONPATH:-}"

# ---- run alembic -----------------------------------------------------------
# Default command is 'upgrade head'; caller may pass alternative args.
ALEMBIC_ARGS="${*:-upgrade head}"

echo "Running: alembic -c ${MIGRATIONS_DIR}/alembic.ini ${ALEMBIC_ARGS}"
cd "${BACKEND_DIR}"
alembic -c "${MIGRATIONS_DIR}/alembic.ini" ${ALEMBIC_ARGS}

echo "Migrations complete"
