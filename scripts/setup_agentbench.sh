#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTBENCH_DIR="${ROOT_DIR}/external/AgentBench"
AGENTBENCH_REPO="${AGENTBENCH_REPO:-https://github.com/THUDM/AgentBench.git}"

mkdir -p "${ROOT_DIR}/external"

if [[ -d "${AGENTBENCH_DIR}/.git" ]]; then
  agentbench_status="existing"
else
  git clone --depth 1 "${AGENTBENCH_REPO}" "${AGENTBENCH_DIR}"
  agentbench_status="cloned"
fi

if command -v docker >/dev/null 2>&1; then
  docker_available="true"
  if docker info >/dev/null 2>&1; then
    docker_daemon_available="true"
  else
    docker_daemon_available="false"
  fi
else
  docker_available="false"
  docker_daemon_available="false"
fi

cat <<EOF
agentbench_status: ${agentbench_status}
agentbench_path: ${AGENTBENCH_DIR}
docker_available: ${docker_available}
docker_daemon_available: ${docker_daemon_available}
note: AgentBench source is ignored by git and remains external to this project.
EOF
