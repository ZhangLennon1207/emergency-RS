#!/usr/bin/env bash
set -euo pipefail

COMMON_SOURCE="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$COMMON_SOURCE")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
ENV_FILE="${AGENT34_ENV_FILE:-$REPO_DEFAULT/.env.agent34}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: Agent34 environment file not found: $ENV_FILE" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${AGENT34_PROJECT_ROOT:?AGENT34_PROJECT_ROOT is required}"
: "${AGENT34_PYTHON_BIN:?AGENT34_PYTHON_BIN is required}"
: "${AGENT34_PID_FILE:?AGENT34_PID_FILE is required}"
: "${AGENT34_LOG_FILE:?AGENT34_LOG_FILE is required}"

mkdir -p "$(dirname "$AGENT34_PID_FILE")" "$(dirname "$AGENT34_LOG_FILE")"
