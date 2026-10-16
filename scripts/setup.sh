#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# setup.sh — First-time project setup for bi-platform
# -----------------------------------------------------------------------------
set -euo pipefail

# ---- colours ----------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

# ---- resolve project root ---------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

info "Project root: ${PROJECT_ROOT}"

# ---- prerequisite checks ----------------------------------------------------
check_command() {
  local cmd="$1"
  local install_hint="${2:-}"
  if ! command -v "${cmd}" &>/dev/null; then
    echo -e "${RED}[MISSING]${RESET} '${cmd}' not found in PATH."
    [[ -n "${install_hint}" ]] && echo "         ${install_hint}"
    return 1
  fi
  local version
  version="$("${cmd}" --version 2>&1 | head -1)"
  success "'${cmd}' found — ${version}"
}

info "Checking prerequisites..."
PREREQ_FAILED=0

check_command docker     "Install Docker Desktop: https://docs.docker.com/get-docker/"         || PREREQ_FAILED=1
check_command "docker"   "" || true
# Verify docker compose v2
if docker compose version &>/dev/null 2>&1; then
  success "docker compose (v2 plugin) found"
elif command -v docker-compose &>/dev/null; then
  warn "Found legacy 'docker-compose' (v1). Consider upgrading to Docker Compose v2."
else
  echo -e "${RED}[MISSING]${RESET} Neither 'docker compose' nor 'docker-compose' found."
  PREREQ_FAILED=1
fi

check_command node   "Install Node.js 20+: https://nodejs.org/"    || PREREQ_FAILED=1
check_command npm    "Comes bundled with Node.js"                  || PREREQ_FAILED=1
check_command python3 "Install Python 3.11+: https://python.org/"  || PREREQ_FAILED=1

# Validate minimum versions
NODE_MAJOR=$(node --version | sed 's/v//' | cut -d. -f1)
if [[ "${NODE_MAJOR}" -lt 18 ]]; then
  error "Node.js 18+ required. Found: $(node --version)"
fi

PYTHON_MINOR=$(python3 --version | awk '{print $2}' | cut -d. -f2)
PYTHON_MAJOR=$(python3 --version | awk '{print $2}' | cut -d. -f1)
if [[ "${PYTHON_MAJOR}" -lt 3 ]] || [[ "${PYTHON_MINOR}" -lt 11 ]]; then
  error "Python 3.11+ required. Found: $(python3 --version)"
fi

[[ "${PREREQ_FAILED}" -eq 1 ]] && error "One or more prerequisites are missing. Please install them and re-run."

# ---- environment file -------------------------------------------------------
info "Setting up environment configuration..."

ENV_FILE="${PROJECT_ROOT}/.env"
ENV_EXAMPLE="${PROJECT_ROOT}/.env.example"

if [[ ! -f "${ENV_EXAMPLE}" ]]; then
  warn ".env.example not found — creating a minimal template."
  cat > "${ENV_EXAMPLE}" <<'ENVEOF'
# ---- Database ----------------------------------------------------------------
POSTGRES_DB=bi_platform
POSTGRES_USER=bi_user
POSTGRES_PASSWORD=change_me_in_production

# ---- Redis -------------------------------------------------------------------
REDIS_PASSWORD=change_me_in_production

# ---- Backend / FastAPI -------------------------------------------------------
SECRET_KEY=change_me_to_a_long_random_string
DEBUG=false
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ORIGINS=http://localhost,http://localhost:3000

# ---- Celery ------------------------------------------------------------------
CELERY_BROKER_URL=redis://:change_me_in_production@localhost:6379/1
CELERY_RESULT_BACKEND=redis://:change_me_in_production@localhost:6379/2

# ---- Frontend ----------------------------------------------------------------
NEXT_PUBLIC_API_URL=http://localhost/api
NEXT_PUBLIC_WS_URL=ws://localhost/ws
ENVEOF
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  success "Created .env from .env.example"
  warn "Review and update ${ENV_FILE} with your actual secrets before production use."
else
  info ".env already exists — skipping copy."
fi

# ---- frontend dependencies --------------------------------------------------
info "Installing frontend dependencies..."

FRONTEND_DIR="${PROJECT_ROOT}/frontend"
if [[ ! -d "${FRONTEND_DIR}" ]]; then
  error "Frontend directory not found: ${FRONTEND_DIR}"
fi

cd "${FRONTEND_DIR}"

if [[ -f "yarn.lock" ]]; then
  yarn install --frozen-lockfile
elif [[ -f "pnpm-lock.yaml" ]]; then
  corepack enable pnpm && pnpm install --frozen-lockfile
else
  npm ci 2>/dev/null || npm install
fi

success "Frontend dependencies installed."

# ---- backend dependencies ---------------------------------------------------
info "Installing backend dependencies..."

BACKEND_DIR="${PROJECT_ROOT}/backend"
if [[ ! -d "${BACKEND_DIR}" ]]; then
  error "Backend directory not found: ${BACKEND_DIR}"
fi

cd "${BACKEND_DIR}"

if command -v poetry &>/dev/null; then
  poetry install --no-root
  success "Backend dependencies installed via Poetry."
elif [[ -f "requirements.txt" ]]; then
  python3 -m pip install --user -r requirements.txt
  success "Backend dependencies installed via pip."
else
  warn "No pyproject.toml or requirements.txt found in ${BACKEND_DIR}. Skipping backend install."
fi

# ---- database migrations ----------------------------------------------------
info "Running database migrations..."

# Start only the infrastructure services needed for migrations
cd "${PROJECT_ROOT}"

COMPOSE_CMD="docker compose"
command -v "docker-compose" &>/dev/null && COMPOSE_CMD="docker-compose"
command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1 && COMPOSE_CMD="docker compose"

"${COMPOSE_CMD}" up -d postgres redis

info "Waiting for PostgreSQL to be ready..."
MAX_WAIT=60
ELAPSED=0
until "${COMPOSE_CMD}" exec -T postgres pg_isready -U "${POSTGRES_USER:-bi_user}" &>/dev/null; do
  if [[ "${ELAPSED}" -ge "${MAX_WAIT}" ]]; then
    error "Timed out waiting for PostgreSQL."
  fi
  printf "."
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done
echo ""
success "PostgreSQL is ready."

cd "${BACKEND_DIR}"

if command -v poetry &>/dev/null; then
  # Load env vars for the migration command
  set -a && source "${ENV_FILE}" && set +a
  DATABASE_URL="postgresql://${POSTGRES_USER:-bi_user}:${POSTGRES_PASSWORD:-change_me_in_production}@localhost:5432/${POSTGRES_DB:-bi_platform}"
  export DATABASE_URL

  if [[ -f "alembic.ini" ]]; then
    poetry run alembic upgrade head && success "Alembic migrations applied."
  else
    warn "alembic.ini not found — skipping migrations."
  fi
else
  warn "Poetry not found — skipping migrations. Run them manually."
fi

# ---- done -------------------------------------------------------------------
echo ""
echo -e "${BOLD}${GREEN}Setup complete!${RESET}"
echo ""
echo -e "  Frontend:  ${CYAN}http://localhost:3000${RESET}"
echo -e "  Backend:   ${CYAN}http://localhost:8000${RESET}"
echo -e "  Full stack (nginx): ${CYAN}http://localhost${RESET}"
echo ""
echo -e "Run ${BOLD}./scripts/start-dev.sh${RESET} to start the development environment."
echo -e "Run ${BOLD}docker compose up --build${RESET} to start the full Docker stack."
