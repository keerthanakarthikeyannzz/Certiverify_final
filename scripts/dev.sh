#!/usr/bin/env bash
# ==============================================================================
# CertiVerify Enterprise - One-Command Dev Server Launcher
# Starts backend with virtualenv interpreter, waits for /health, then starts frontend.
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# Read environment variables with documented defaults.
# CRITICAL: Separate frontend port (PORT / FRONTEND_PORT) and backend port (BACKEND_PORT).
# Never fall back BACKEND_PORT to PORT.
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-${PORT:-3000}}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT_SECONDS:-30}"
HEALTH_PATH="${HEALTH_PATH:-/health}"
BACKEND_RELOAD_DIR="${BACKEND_RELOAD_DIR:-app}"

export BACKEND_HOST
export BACKEND_PORT
export FRONTEND_PORT
export FRONTEND_HOST
export BACKEND_URL="${BACKEND_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}}"
export NEXT_PUBLIC_API_URL="$BACKEND_URL"
export NEXT_PUBLIC_API_BASE_URL="$BACKEND_URL"
export NEXT_PUBLIC_BACKEND_URL="$BACKEND_URL"
export NEXT_PUBLIC_FRONTEND_PORT="$FRONTEND_PORT"
export NEXT_PUBLIC_HEALTH_PATH="$HEALTH_PATH"

echo "=========================================================="
echo " Starting CertiVerify Enterprise Stack"
echo " Backend Target:  $BACKEND_URL"
echo " Frontend Target: http://${FRONTEND_HOST}:$FRONTEND_PORT"
echo "=========================================================="

# 0. Loop Guard: compare resolved backend URL with frontend port
if [ "$BACKEND_PORT" = "$FRONTEND_PORT" ]; then
  case "$BACKEND_HOST" in
    127.0.0.1|localhost|0.0.0.0|::1)
      echo ""
      echo "❌ [LOOP GUARD ERROR] BACKEND_URL points to the frontend itself: $BACKEND_URL"
      echo "   Frontend port ($FRONTEND_PORT) and backend port ($BACKEND_PORT) cannot be equal on local host."
      echo "   To fix: set BACKEND_PORT=8000 (or BACKEND_URL=http://127.0.0.1:8000) and FRONTEND_PORT=3000."
      exit 1
      ;;
  esac
fi

# 1. Check if backend port is already in use
OCCUPYING_PID=$(lsof -tiTCP:"$BACKEND_PORT" 2>/dev/null | head -n 1 || true)
if [ -z "$OCCUPYING_PID" ]; then
  OCCUPYING_PID=$(lsof -ti :"$BACKEND_PORT" 2>/dev/null | head -n 1 || true)
fi

if [ -n "$OCCUPYING_PID" ] && kill -0 "$OCCUPYING_PID" 2>/dev/null; then
  echo ""
  echo "❌ Port $BACKEND_PORT is already in use by process PID $OCCUPYING_PID!"
  echo "Process information:"
  ps -fp "$OCCUPYING_PID" 2>/dev/null || lsof -i :"$BACKEND_PORT"
  echo ""
  echo "Action required:"
  echo "  - Terminate the occupying process: kill -9 $OCCUPYING_PID"
  echo "  - OR run on a different port:      BACKEND_PORT=8001 ./scripts/dev.sh"
  exit 1
fi

FRONTEND_OCCUPYING_PID=$(lsof -tiTCP:"$FRONTEND_PORT" 2>/dev/null | head -n 1 || true)
if [ -n "$FRONTEND_OCCUPYING_PID" ] && kill -0 "$FRONTEND_OCCUPYING_PID" 2>/dev/null; then
  echo ""
  echo "❌ Frontend port $FRONTEND_PORT is already in use by PID $FRONTEND_OCCUPYING_PID!"
  ps -fp "$FRONTEND_OCCUPYING_PID" 2>/dev/null || lsof -i :"$FRONTEND_PORT"
  echo "Please stop the occupying process (kill -9 $FRONTEND_OCCUPYING_PID) or specify FRONTEND_PORT=3001"
  exit 1
fi

# 2. Locate Python virtual environment
PYTHON_BIN=""
if [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"
elif [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "❌ ERROR: No Python interpreter found!"
  echo "Please set up the backend virtualenv: cd backend && python3 -m venv .venv && pip install -r requirements.txt"
  exit 1
fi

echo "✔ Using Python interpreter: $PYTHON_BIN"

# 3. Setup cleanup trap
BACKEND_PID=""
cleanup() {
  echo ""
  echo "Shutting down servers..."
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
  echo "Servers stopped."
}
trap cleanup SIGINT SIGTERM EXIT

# 4. Start backend in background
# Limit reload watching to the app directory and exclude virtualenv, node_modules, and uploads
echo "Starting backend (uvicorn) on $BACKEND_HOST:$BACKEND_PORT (watching $BACKEND_RELOAD_DIR)..."
(
  cd "$BACKEND_DIR"

  EXCLUDE_ARGS=("--reload-exclude" "*.db*" "--reload-exclude" "*.log" "--reload-exclude" "uploads/*" "--reload-exclude" "data/*" "--reload-exclude" "scripts/*")
  [ -d "$BACKEND_DIR/.venv" ] && EXCLUDE_ARGS+=("--reload-exclude" "$BACKEND_DIR/.venv")
  [ -d "$ROOT_DIR/.venv" ] && EXCLUDE_ARGS+=("--reload-exclude" "$ROOT_DIR/.venv")
  [ -d "$BACKEND_DIR/uploads" ] && EXCLUDE_ARGS+=("--reload-exclude" "$BACKEND_DIR/uploads" "--reload-exclude" "$BACKEND_DIR/uploads/*")
  [ -d "$BACKEND_DIR/data" ] && EXCLUDE_ARGS+=("--reload-exclude" "$BACKEND_DIR/data" "--reload-exclude" "$BACKEND_DIR/data/*")
  [ -d "$BACKEND_DIR/scripts" ] && EXCLUDE_ARGS+=("--reload-exclude" "$BACKEND_DIR/scripts" "--reload-exclude" "$BACKEND_DIR/scripts/*")
  [ -d "$ROOT_DIR/scripts" ] && EXCLUDE_ARGS+=("--reload-exclude" "$ROOT_DIR/scripts" "--reload-exclude" "$ROOT_DIR/scripts/*")
  [ -d "$FRONTEND_DIR/node_modules" ] && EXCLUDE_ARGS+=("--reload-exclude" "$FRONTEND_DIR/node_modules")
  [ -d "$ROOT_DIR/node_modules" ] && EXCLUDE_ARGS+=("--reload-exclude" "$ROOT_DIR/node_modules")

  exec "$PYTHON_BIN" -m uvicorn app.main:app \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" \
    --reload \
    --reload-dir "$BACKEND_RELOAD_DIR" \
    "${EXCLUDE_ARGS[@]}"
) &
BACKEND_PID=$!

# 5. Wait for /health endpoint to respond 200 OK
HEALTH_URL="http://${BACKEND_HOST}:${BACKEND_PORT}${HEALTH_PATH}"
echo "Waiting for backend health probe ($HEALTH_URL, timeout: ${HEALTH_TIMEOUT}s)..."

START_TIME=$(date +%s)
while true; do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 2 "$HEALTH_URL" 2>/dev/null || true)
  if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Backend is healthy! ($HEALTH_URL returned HTTP 200)"
    break
  fi

  # Check if backend crashed
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "❌ ERROR: Backend process died during startup! Inspect the logs above."
    exit 1
  fi

  NOW=$(date +%s)
  ELAPSED=$((NOW - START_TIME))
  if [ "$ELAPSED" -ge "$HEALTH_TIMEOUT" ]; then
    echo "❌ ERROR: Health probe timed out after ${HEALTH_TIMEOUT}s (last HTTP status: ${HTTP_CODE:-none})."
    exit 1
  fi
  sleep 0.5
done

# 6. Start frontend
echo "Starting frontend Next.js dev server on port $FRONTEND_PORT..."
cd "$FRONTEND_DIR"
PORT="$FRONTEND_PORT" npm run dev
