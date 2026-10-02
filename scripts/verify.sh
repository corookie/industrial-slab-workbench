#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
(cd frontend && npm run build)
if [ "${1:-}" = '--browser' ]; then
  (cd frontend && npm run test:e2e)
fi
