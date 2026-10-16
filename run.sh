#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

# Prefer conda/miniforge Python 3.13 over the system python3 (Homebrew 3.14 has
# a broken pyexpat — see https://github.com/Homebrew/homebrew-core/issues on
# _XML_SetAllocTrackerActivationThreshold symbol mismatch with system libexpat).
CONDA_PYTHON="/opt/homebrew/Caskroom/miniforge/base/bin/python3.13"
if [ -x "$CONDA_PYTHON" ]; then
  PYTHON="$CONDA_PYTHON"
  PIP="$CONDA_PYTHON -m pip"
else
  PYTHON="python3"
  PIP="pip3"
fi

# ── 1. Environment ──────────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/config/.env.example" "$ROOT/.env"
  # Use SQLite so no database install is needed
  sed -i '' 's|DATABASE_URL=postgresql+asyncpg://[^"]*|DATABASE_URL=sqlite+aiosqlite:///./biplatform.db|' "$ROOT/.env"
  sed -i '' 's|DATABASE_URL_SYNC=postgresql://[^"]*|DATABASE_URL_SYNC=sqlite:///./biplatform.db|' "$ROOT/.env"
fi

# ── 2. Backend dependencies ─────────────────────────────────────────────────
echo "[1/5] Installing backend dependencies..."
cd "$BACKEND"
$PIP install -q -r requirements.txt
$PYTHON -m playwright install chromium --with-deps 2>/dev/null || $PYTHON -m playwright install chromium

# ── 3. Database init + seed ──────────────────────────────────────────────────
echo "[2/5] Initialising database..."
cd "$BACKEND"
$PYTHON - <<'PY'
import asyncio, sys, os
sys.path.insert(0, ".")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./biplatform.db")
from app.core.database import init_db
asyncio.run(init_db())
print("  Database ready.")
PY

echo "[3/5] Seeding sample data..."
$PYTHON - <<'PY'
import asyncio, sys, os
sys.path.insert(0, ".")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./biplatform.db")
try:
    from database.seeds.seed_data import run_seed
    asyncio.run(run_seed())
except Exception as e:
    print(f"  Seed skipped ({e})")
PY

# ── 4. Frontend dependencies ─────────────────────────────────────────────────
echo "[4/5] Installing frontend dependencies..."
cd "$FRONTEND"
npm install --silent

# ── 5. Launch ────────────────────────────────────────────────────────────────
echo "[5/5] Starting servers..."
echo ""
echo "  Backend  →  http://localhost:8000"
echo "  API Docs →  http://localhost:8000/docs"
echo "  Frontend →  http://localhost:3000"
echo "  Login    →  admin@biplatform.com / admin123"
echo ""
echo "  Press Ctrl+C to stop."
echo ""

# Start backend in background
cd "$BACKEND"
$PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start frontend
cd "$FRONTEND"
npm run dev -- --hostname 0.0.0.0 &
FRONTEND_PID=$!

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
