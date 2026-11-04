#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
portle_python="${PORTLE_PYTHON:-python3}"
if [[ ! -x .venv/bin/python ]]; then "$portle_python" -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
if [[ $# -gt 0 ]]; then exec .venv/bin/python -m portle import-assets "$@"; fi
exec .venv/bin/python -m portle doctor
