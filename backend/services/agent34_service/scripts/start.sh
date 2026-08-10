#!/usr/bin/env bash
set -euo pipefail
SCRIPT_SOURCE="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

if [[ -f "$AGENT34_PID_FILE" ]]; then
    old_pid="$(cat "$AGENT34_PID_FILE")"
    if kill -0 "$old_pid" 2>/dev/null; then
        echo "Agent34 is already running (PID=$old_pid)"
        exit 0
    fi
    rm -f "$AGENT34_PID_FILE"
fi

cd "$AGENT34_PROJECT_ROOT"
export PYTHONPATH="$AGENT34_PROJECT_ROOT"
nohup "$AGENT34_PYTHON_BIN" -m uvicorn \
    backend.services.agent34_service.main:app \
    --host 127.0.0.1 --port 8100 --workers 1 \
    >>"$AGENT34_LOG_FILE" 2>&1 &
pid=$!
echo "$pid" >"$AGENT34_PID_FILE"

for _ in {1..30}; do
    if curl -fsS http://127.0.0.1:8100/api/v1/health >/dev/null; then
        echo "Agent34 started (PID=$pid, listen=127.0.0.1:8100)"
        exit 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "ERROR: Agent34 exited during startup; inspect AGENT34_LOG_FILE" >&2
        rm -f "$AGENT34_PID_FILE"
        exit 1
    fi
    sleep 1
done

echo "ERROR: Agent34 health check timed out" >&2
exit 1
