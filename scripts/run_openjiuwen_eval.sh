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

export DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-v4-flash}"
export DEEPSEEK_API_BASE="${DEEPSEEK_API_BASE:-https://api.deepseek.com}"
export MODEL_PROVIDER="${MODEL_PROVIDER:-openai}"
export OPENJIUWEN_EVAL_LIMIT="${OPENJIUWEN_EVAL_LIMIT:-3}"

if [ "$#" -gt 0 ]; then
  "$PYTHON_BIN" -m knowledge_agent.evaluation.openjiuwen_runner "$@"
else
  "$PYTHON_BIN" -m knowledge_agent.evaluation.openjiuwen_runner --agent both --limit "$OPENJIUWEN_EVAL_LIMIT"
fi
