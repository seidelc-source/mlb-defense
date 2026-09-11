#!/usr/bin/env bash
# Serve the FULL live app from this machine behind a free Cloudflare quick
# tunnel: builds the frontend for single-origin serving, starts the backend
# in PUBLIC_MODE (mutation endpoints locked), and prints a shareable
# https://*.trycloudflare.com URL. The URL lives until you Ctrl-C.
#
# Prereqs: Postgres + Redis running (see STARTUP.md), cloudflared installed
# (brew install cloudflared).
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"

echo "→ Building frontend (single-origin, /api/v1)…"
(cd frontend && VITE_API_BASE_URL=/api/v1 npm run build --silent)

echo "→ Starting backend on :$PORT (PUBLIC_MODE=1 — ingest/injury mutations locked)…"
(cd backend && PUBLIC_MODE=1 .venv/bin/python -m uvicorn app.main:app --port "$PORT") &
BACKEND_PID=$!

TUNNEL_LOG="$(mktemp)"
cleanup() {
  kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "${TUNNEL_PID:-}" ] && kill "$TUNNEL_PID" 2>/dev/null || true
  rm -f "$TUNNEL_LOG"
}
trap cleanup EXIT

for _ in $(seq 1 30); do
  curl -sf "http://localhost:$PORT/health" >/dev/null && break
  sleep 1
done
curl -sf "http://localhost:$PORT/health" >/dev/null || {
  echo "backend failed to start"; exit 1; }

echo "→ Opening Cloudflare quick tunnel…"
cloudflared tunnel --url "http://localhost:$PORT" >"$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

URL=""
for _ in $(seq 1 30); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -1 || true)"
  [ -n "$URL" ] && break
  sleep 1
done

if [ -n "$URL" ]; then
  echo ""
  echo "════════════════════════════════════════════════════"
  echo "  Live app (share this):  $URL"
  echo "  Local:                  http://localhost:$PORT"
  echo "  Stops when you Ctrl-C or close this terminal."
  echo "════════════════════════════════════════════════════"
else
  echo "Tunnel URL not found — see $TUNNEL_LOG. App is still on http://localhost:$PORT"
fi

wait "$BACKEND_PID"
