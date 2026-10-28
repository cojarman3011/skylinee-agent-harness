#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -e .
if [[ ! -f .env ]]; then
  .venv/bin/python -m skylinee_harness.cli init "$@"
fi
exec .venv/bin/python -m skylinee_harness.cli serve
