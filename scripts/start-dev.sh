#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# start-dev.sh — Start bi-platform in development mode
#
# Services started:
#   • postgres + redis via Docker Compose
#   • FastAPI backend with --reload
#   • Celery worker
#   • Next.js frontend with hot-reload
#
# Usage:  ./scripts/start-dev.sh
# Stop:   Ctrl-C (all background processes are cleaned up automatically)
# -----------------------------------------------------------------------------
set -euo pipefail

# ---- colours ----------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

# ---- resolve paths ----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"

ENV_FILE="${PROJECT_ROOT}/.env"
[[ -f "${ENV_FILE}" ]] || error ".env not found — run ./scripts/setup.sh first."

# Load environment variables
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

# ---- PID tracking for cleanup -----------------------------------------------
PIDS=()

cleanup() {
  echo ""
  info "Shutting down all development services..."

  for pid in "${PIDS[@]}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
    fi
  done

  # Give processes a moment to terminate gracefully
  sleep 1

  for pid in "${PIDS[@]}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      kill -9 "${pid}" 2>/dev/null || true
    fi
  done

  info "Stopping Docker infrastructure..."
  cd "${PROJECT_ROOT}"
  COMPOSE_CMD="docker compose"
  docker compose version &>/dev/null 2>&1 || COMPOSE_CMD="docker-compose"
  "${COMPOSE_CMD}" stop postgres redis 2>/dev/null || true

  success "Development environment stopped."
}

trap cleanup SIGINT SIGTERM EXIT

# ---- docker compose command -----------------------------------------------------------------
COMPOSE_CMD="docker compose"
docker compose version &>/dev/null 2>&1 || COMPOSE_CMD="docker-compose"
command -v "${COMPOSE_CMD%% *}" &>/dev/null || error "Docker Compose not found. Install Docker Desktop."

# ---- 1. Start infrastructure ------------------------------------------------
info "Starting PostgreSQL and Redis..."
cd "${PROJECT_ROOT}"
"${COMPOSE_CMD}" up -d postgres redis

info "Waiting for PostgreSQL to be ready..."
MAX_WAIT=60
ELAPSED=0
until "${COMPOSE_CMD}" exec -T postgres pg_isready \
    -U "${POSTGRES_USER:-bi_user}" \
    -d "${POSTGRES_DB:-bi_platform}" &>/dev/null; do
  if [[ "${ELAPSED}" -ge "${MAX_WAIT}" ]]; then
    error "Timed out waiting for PostgreSQL."
  fi
  printf "."
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done
echo ""
success "PostgreSQL is ready."

info "Waiting for Redis to be ready..."
ELAPSED=0
until "${COMPOSE_CMD}" exec -T redis redis-cli \
    -a "${REDIS_PASSWORD:-redis_secret}" ping 2>/dev/null | grep -q PONG; do
  if [[ "${ELAPSED}" -ge 30 ]]; then
    error "Timed out waiting for Redis."
  fi
  printf "."
  sleep 1
  ELAPSED=$((ELAPSED + 1))
done
echo ""
success "Redis is ready."

# ---- 2. Backend — uvicorn with hot-reload -----------------------------------
mkdir -p "${PROJECT_ROOT}/logs"

info "Starting FastAPI backend (http://localhost:8000)..."

cd "${BACKEND_DIR}"

# Determine runner (poetry vs plain python)
if command -v poetry &>/dev/null && [[ -f "pyproject.toml" ]]; then
  RUNNER="poetry run"
else
  RUNNER=""
fi

DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER:-bi_user}:${POSTGRES_PASSWORD:-change_me_in_production}@localhost:5432/${POSTGRES_DB:-bi_platform}"
REDIS_URL="redis://:${REDIS_PASSWORD:-redis_secret}@localhost:6379/0"
CELERY_BROKER_URL="redis://:${REDIS_PASSWORD:-redis_secret}@localhost:6379/1"
CELERY_RESULT_BACKEND="redis://:${REDIS_PASSWORD:-redis_secret}@localhost:6379/2"
export DATABASE_URL REDIS_URL CELERY_BROKER_URL CELERY_RESULT_BACKEND

${RUNNER} uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --reload-dir "${BACKEND_DIR}/app" \
  --log-level info \
  > "${PROJECT_ROOT}/logs/backend.log" 2>&1 &

BACKEND_PID=$!
PIDS+=("${BACKEND_PID}")
success "Backend started (PID ${BACKEND_PID}) — logs: logs/backend.log"

# ---- 3. Celery worker -------------------------------------------------------
info "Starting Celery worker..."

cd "${BACKEND_DIR}"

${RUNNER} celery -A app.workers.celery_app worker \
  --loglevel=info \
  --concurrency=2 \
  -Q default,reports,scraping \
  > "${PROJECT_ROOT}/logs/celery-worker.log" 2>&1 &

CELERY_PID=$!
PIDS+=("${CELERY_PID}")
success "Celery worker started (PID ${CELERY_PID}) — logs: logs/celery-worker.log"

# ---- 4. Frontend — next dev -------------------------------------------------
info "Starting Next.js frontend (http://localhost:3000)..."

cd "${FRONTEND_DIR}"

# Determine package manager
if [[ -f "yarn.lock" ]]; then
  FE_CMD="yarn dev"
elif [[ -f "pnpm-lock.yaml" ]]; then
  FE_CMD="pnpm run dev"
else
  FE_CMD="npm run dev"
fi

NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8000}" \
NEXT_PUBLIC_WS_URL="${NEXT_PUBLIC_WS_URL:-ws://localhost:8000/ws}" \
${FE_CMD} \
  > "${PROJECT_ROOT}/logs/frontend.log" 2>&1 &

FRONTEND_PID=$!
PIDS+=("${FRONTEND_PID}")
success "Frontend started (PID ${FRONTEND_PID}) — logs: logs/frontend.log"

# ---- Summary ----------------------------------------------------------------
echo ""
echo -e "${BOLD}${GREEN}Development environment running!${RESET}"
echo ""
echo -e "  ${BOLD}Frontend:${RESET}  ${CYAN}http://localhost:3000${RESET}"
echo -e "  ${BOLD}Backend:${RESET}   ${CYAN}http://localhost:8000${RESET}"
echo -e "  ${BOLD}API docs:${RESET}  ${CYAN}http://localhost:8000/docs${RESET}"
echo ""
echo -e "  Logs directory: ${BOLD}${PROJECT_ROOT}/logs/${RESET}"
echo ""
echo -e "Press ${BOLD}Ctrl-C${RESET} to stop all services."
echo ""

# ---- Wait for all background processes --------------------------------------
# Keep the script running so the trap fires on Ctrl-C
wait
