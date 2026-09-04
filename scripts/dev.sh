#!/usr/bin/env bash
# Start the whole local stack: LiteLLM gateway, API, and frontend.
#
#   ./scripts/dev.sh
#
# Sources scripts/env.sh first so httpx trusts this machine's TLS-terminating
# ZTNA agent; without it the API cannot reach the MCP tool server over HTTPS.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
# shellcheck disable=SC1091
. "$REPO_ROOT/scripts/env.sh"

cleanup() { echo; echo "Stopping..."; kill 0 2>/dev/null; }
trap cleanup EXIT INT TERM

for PORT in 8000 5173; do
    PIDS="$(lsof -ti "tcp:$PORT" 2>/dev/null || true)"
    [ -n "$PIDS" ] && { echo "Freeing port $PORT"; kill $PIDS 2>/dev/null || true; sleep 1; }
done

# Vite 8 needs a Node with util.styleText (20.12+). The shell default here has
# been both 20.11.0 and 20.18.1 at different times, and on the older one Vite
# dies with "does not provide an export named 'styleText'" -- which reads like a
# dependency bug rather than a version mismatch. Pin it from web/.nvmrc.
if [ -s "$HOME/.nvm/nvm.sh" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.nvm/nvm.sh"
    (cd "$REPO_ROOT/web" && nvm use >/dev/null 2>&1) || true
    nvm use "$(cat "$REPO_ROOT/web/.nvmrc" 2>/dev/null || echo 20.18.1)" >/dev/null 2>&1 || true
fi
echo "Node: $(node -v)"

echo "==> Gateway"
docker compose up -d litellm

echo
echo "Gateway  http://127.0.0.1:4000"
echo "API      http://127.0.0.1:8000  (docs at /docs)"
echo "Frontend http://127.0.0.1:5173"
echo

( cd backend && "$REPO_ROOT/.venv/bin/python" -m uvicorn app.main:app \
    --host 127.0.0.1 --port 8000 --log-level info 2>&1 | sed 's/^/[api] /' ) &
( cd web && npx vite --host 127.0.0.1 --port 5173 2>&1 | sed 's/^/[web] /' ) &

wait
