#!/usr/bin/env bash
TARGET="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || realpath "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$TARGET")" && pwd)"
exec python3 "$SCRIPT_DIR/repl.py" "$@"
