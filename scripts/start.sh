#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  task_python="${PYTHON_BOOTSTRAP:-}"
  if [ -z "$task_python" ]; then
    if command -v python3.12 >/dev/null 2>&1; then
      task_python="$(command -v python3.12)"
    elif [ -x /Users/rowen/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 ]; then
      task_python=/Users/rowen/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
    else
      task_python="$(command -v python3)"
    fi
  fi
  "$task_python" -c 'import sys; assert sys.version_info >= (3,10), "Requires Python 3.10+; set PYTHON_BOOTSTRAP to its executable"'
  "$task_python" -m venv .venv
fi
if ! .venv/bin/python -c 'import fastapi,uvicorn,pandas,matplotlib,openpyxl,multipart,scipy,dotenv' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r backend/requirements.lock.txt
fi
if [ ! -d frontend/node_modules ]; then (cd frontend && npm ci --no-audit --no-fund); fi
(cd frontend && npm run build)
task_open=false
for task_arg in "$@"; do
  case "$task_arg" in
    --private) export SLAB_MODE=private ;;
    --public) export SLAB_MODE=public ;;
    --open) task_open=true ;;
    *) printf '未知启动参数：%s\n' "$task_arg"; exit 1 ;;
  esac
done
task_port="${PORT:-8765}"
printf '\n工作台地址：http://127.0.0.1:%s\n关闭终端或按 Ctrl+C 停止服务。\n\n' "$task_port"
if [ "$task_open" = true ]; then
  .venv/bin/python scripts/open_when_ready.py "$task_port" &
fi
exec .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port "$task_port"
