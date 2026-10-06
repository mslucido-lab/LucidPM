#!/bin/bash
set -e

cleanup() {
    kill "$BACKEND_PID" "$CADDY_PID" 2>/dev/null || true
    wait "$BACKEND_PID" "$CADDY_PID" 2>/dev/null || true
}

trap 'cleanup; exit 143' INT TERM

reflex run --env prod --backend-only --backend-host 127.0.0.1 --backend-port 8000 &
BACKEND_PID=$!

# Caddy serves the static SPA shell the instant it starts, but its
# reverse-proxied routes (notably the /_event WebSocket) 502 until the Reflex
# backend is actually accepting connections. Starting Caddy concurrently with
# the backend let that race reach real users on a cold start (scale-from-
# zero): the page loaded, then its first websocket connect hit the 502 and
# surfaced as a hard "Cannot connect to server: websocket error" instead of
# Container Apps' normal scale-from-zero request queuing (which only works if
# the ingress port stays closed until the app behind it can actually serve).
# So: don't open 8080 at all until the backend's own health endpoint answers.
READY_TIMEOUT=90
elapsed=0
until python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ping', timeout=2).status==200 else 1)" 2>/dev/null; do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "entrypoint: backend process exited before becoming ready" >&2
        wait "$BACKEND_PID"
        exit $?
    fi
    if [ "$elapsed" -ge "$READY_TIMEOUT" ]; then
        echo "entrypoint: backend did not become ready within ${READY_TIMEOUT}s" >&2
        cleanup
        exit 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
done

caddy run --config /app/Caddyfile --adapter caddyfile &
CADDY_PID=$!

# If either process exits, stop the other so the container never continues to
# serve static files while its Reflex backend is unavailable.
wait -n "$BACKEND_PID" "$CADDY_PID"
EXIT_CODE=$?
cleanup
exit "$EXIT_CODE"
