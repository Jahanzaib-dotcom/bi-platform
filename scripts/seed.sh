#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# seed.sh — populate the database with sample data
#
# Usage:
#   bash scripts/seed.sh
#
# Environment variables honoured:
#   DATABASE_URL  — overrides the default SQLite path (optional)
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
SEED_SCRIPT="${PROJECT_ROOT}/database/seeds/seed_data.py"

# ---- validate ---------------------------------------------------------------
if [ ! -d "${BACKEND_DIR}" ]; then
    echo "ERROR: backend directory not found at ${BACKEND_DIR}" >&2
    exit 1
fi

if [ ! -f "${SEED_SCRIPT}" ]; then
    echo "ERROR: seed script not found at ${SEED_SCRIPT}" >&2
    exit 1
fi

# ---- load .env if present ---------------------------------------------------
ENV_FILE="${PROJECT_ROOT}/config/.env"
if [ -f "${ENV_FILE}" ]; then
    # shellcheck disable=SC2046
    export $(grep -v '^#' "${ENV_FILE}" | xargs -d '\n') 2>/dev/null || true
fi

# ---- ensure the backend package is importable -------------------------------
export PYTHONPATH="${BACKEND_DIR}:${PYTHONPATH:-}"

# ---- run seed ---------------------------------------------------------------
echo "Seeding database..."
cd "${BACKEND_DIR}"
python "${SEED_SCRIPT}"

echo "Seed complete"
