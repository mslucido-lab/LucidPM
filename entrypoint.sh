#!/bin/bash
set -e

cleanup() {
    kill "$BACKEND_PID" "$CADDY_PID" 2>/dev/null || true
    wait "$BACKEND_PID" "$CADDY_PID" 2>/dev/null || true
}

reflex run --env prod --backend-only --backend-host 127.0.0.1 --backend-port 8000 &
BACKEND_PID=$!

caddy run --config /app/Caddyfile --adapter caddyfile &
CADDY_PID=$!

trap 'cleanup; exit 143' INT TERM

# If either process exits, stop the other so the container never continues to
# serve static files while its Reflex backend is unavailable.
wait -n "$BACKEND_PID" "$CADDY_PID"
EXIT_CODE=$?
cleanup
exit "$EXIT_CODE"
