#!/usr/bin/env bash
TARGET="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || realpath "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$TARGET")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

# Read only the interpreter path from .env. Do not source the file because it
# also contains application secrets and is parsed as dotenv by the Python app.
if [[ -z "${PROJECTK_VENV:-}" && -f "$ENV_FILE" ]]; then
    PROJECTK_VENV="$(sed -nE 's/^[[:space:]]*(export[[:space:]]+)?PROJECTK_VENV[[:space:]]*=[[:space:]]*//p' "$ENV_FILE" | tail -n 1 | tr -d '\r')"
fi
PROJECTK_VENV="${PROJECTK_VENV#\"}"
PROJECTK_VENV="${PROJECTK_VENV%\"}"
PROJECTK_VENV="${PROJECTK_VENV#\'}"
PROJECTK_VENV="${PROJECTK_VENV%\'}"
case "$PROJECTK_VENV" in
    "~/"*) PROJECTK_VENV="$HOME/${PROJECTK_VENV#\~/}" ;;
    "~") PROJECTK_VENV="$HOME" ;;
esac

if [[ -z "$PROJECTK_VENV" ]]; then
    echo "Set PROJECTK_VENV in $ENV_FILE to the external uv environment path." >&2
    exit 1
fi

PYTHON="$PROJECTK_VENV/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "Python was not found in PROJECTK_VENV: $PYTHON" >&2
    echo "Create it with: uv venv \"$PROJECTK_VENV\"" >&2
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/repl.py" "$@"
