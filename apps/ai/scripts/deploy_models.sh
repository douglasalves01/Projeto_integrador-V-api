#!/usr/bin/env bash
# Package and deploy LLM/classic model artifacts to a remote AI service host.
set -euo pipefail

TAG="${1:-vodrec-v1.0.0}"
VOD_AI_HOST="${VOD_AI_HOST:-user@your-ai-host}"
VOD_ADMIN_KEY="${VOD_ADMIN_KEY:-change-me-ai-api-key}"
REMOTE_DIR="${REMOTE_DIR:-/opt/vod-ai}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODELS_DIR="${MODELS_DIR:-${ROOT}/models}"

if [[ ! -d "${MODELS_DIR}" ]]; then
  echo "Models directory not found: ${MODELS_DIR}" >&2
  exit 1
fi

ARCHIVE="${TAG}.tar.gz"
tar -czf "${ARCHIVE}" -C "${MODELS_DIR}" .

scp "${ARCHIVE}" "${VOD_AI_HOST}:${REMOTE_DIR}/incoming/"
ssh "${VOD_AI_HOST}" "
  set -euo pipefail
  mkdir -p ${REMOTE_DIR}/models ${REMOTE_DIR}/incoming
  tar -xzf ${REMOTE_DIR}/incoming/${ARCHIVE} -C ${REMOTE_DIR}/models/
  curl -sf -X POST http://localhost:8000/api/v1/admin/reload-models \
    -H 'X-AI-API-Key: ${VOD_ADMIN_KEY}'
  echo
"

rm -f "${ARCHIVE}"
echo "Deploy complete: ${TAG}"
