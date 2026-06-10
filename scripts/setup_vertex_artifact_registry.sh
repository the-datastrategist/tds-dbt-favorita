#!/usr/bin/env bash
# One-time GCP setup for Vertex pipeline submit (run with a user or admin account, not the Cursor SA).
#
#   gcloud auth login
#   bash scripts/setup_vertex_artifact_registry.sh
#
# Then push the image and submit:
#   gcloud auth configure-docker us-central1-docker.pkg.dev
#   make vertex-docker-push
#   make vertex-pipeline-submit VERTEX_PIPELINE=favorita_store_n1d_rf

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PROJECT="${GOOGLE_PROJECT_ID:?Set GOOGLE_PROJECT_ID in .env}"
REGION="${VERTEX_AI_REGION:-${GOOGLE_REGION:-us-central1}}"
REPO="${ARTIFACT_REGISTRY_REPO:-vertex}"

echo "Project: ${PROJECT}"
echo "Region:  ${REGION}"
echo "Repo:    ${REPO}"
echo ""

echo "=== Enable APIs ==="
gcloud services enable \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  --project="${PROJECT}"

echo "=== Create Artifact Registry repo (idempotent) ==="
if gcloud artifacts repositories describe "${REPO}" \
  --project="${PROJECT}" \
  --location="${REGION}" >/dev/null 2>&1; then
  echo "Repository ${REPO} already exists."
else
  gcloud artifacts repositories create "${REPO}" \
    --project="${PROJECT}" \
    --location="${REGION}" \
    --repository-format=docker \
    --description="tds-favorita Vertex training and pipeline image"
fi

echo "=== Next steps ==="
echo "1. gcloud auth login   # your user account (Owner or Artifact Registry Writer)"
echo "2. make vertex-docker-push"
echo "3. make vertex-gcp-check"
echo "4. make vertex-pipeline-submit VERTEX_PIPELINE=favorita_store_n1d_rf"
