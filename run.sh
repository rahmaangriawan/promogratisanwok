#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv; ./.venv/bin/pip -q install -r requirements.txt; }
exec ./.venv/bin/python -m pantau.cli "$@"
