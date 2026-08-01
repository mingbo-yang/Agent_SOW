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

if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  echo "missing DEEPSEEK_API_KEY" >&2
  exit 2
fi

export API_KEY="$DEEPSEEK_API_KEY"
export API_BASE="${DEEPSEEK_API_BASE:-https://api.deepseek.com}"
export MODEL_PROVIDER="${MODEL_PROVIDER:-openai}"
export MODEL_NAME="${DEEPSEEK_MODEL:-deepseek-v4-flash}"
export LLM_SSL_VERIFY="${LLM_SSL_VERIFY:-false}"
export OPENJIUWEN_API_KEY="$DEEPSEEK_API_KEY"
export OPENJIUWEN_API_BASE="$API_BASE"

".venv/bin/openjiuwen" --provider "$MODEL_PROVIDER" --api-base "$API_BASE" --model "$MODEL_NAME" run \
  --output-format text \
  "Return exactly: openjiuwen deepseek api reachable"
