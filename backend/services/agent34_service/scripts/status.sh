#!/usr/bin/env bash
set -euo pipefail
SCRIPT_SOURCE="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

if [[ ! -f "$AGENT34_PID_FILE" ]]; then
    echo "STOPPED"
    exit 1
fi
pid="$(cat "$AGENT34_PID_FILE")"
if ! kill -0 "$pid" 2>/dev/null; then
    echo "STALE PID=$pid"
    exit 1
fi
echo "RUNNING PID=$pid listen=127.0.0.1:8100"
curl -fsS http://127.0.0.1:8100/api/v1/health
echo
