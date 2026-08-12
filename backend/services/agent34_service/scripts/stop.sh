#!/usr/bin/env bash
set -euo pipefail
SCRIPT_SOURCE="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

if [[ ! -f "$AGENT34_PID_FILE" ]]; then
    echo "Agent34 is stopped"
    exit 0
fi
pid="$(cat "$AGENT34_PID_FILE")"
if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    for _ in {1..20}; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.5
    done
fi
rm -f "$AGENT34_PID_FILE"
echo "Agent34 stopped"
