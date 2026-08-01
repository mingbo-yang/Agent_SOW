#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" - <<'PY'
from knowledge_agent.adapters.openjiuwen import OpenJiuwenRuntimeAdapter

print({"openjiuwen_available": OpenJiuwenRuntimeAdapter.is_available()})
PY

