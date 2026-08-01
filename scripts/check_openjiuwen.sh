#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi
"$PYTHON_BIN" - <<'PY'
from knowledge_agent.adapters.openjiuwen import OpenJiuwenRuntimeAdapter

print({"openjiuwen_available": OpenJiuwenRuntimeAdapter.is_available()})
PY
