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
try:
    from openjiuwen.core.single_agent.agents.react_agent import ReActAgent, ReActAgentConfig
except Exception as exc:
    print({"openjiuwen_available": False, "error": str(exc)})
else:
    print(
        {
            "openjiuwen_available": True,
            "react_agent": ReActAgent.__name__,
            "config": ReActAgentConfig.__name__,
        }
    )

PY
