#!/usr/bin/env bash
# Build the local ml-pipeline image and push to Artifact Registry for Vertex jobs.
#
# Prerequisites:
#   make vertex-gcp-setup   # once, with gcloud admin login
#   gcloud auth login       # your user account (not only the Cursor SA)
#
# Docker Desktop on macOS: credsStore "desktop" can block the gcloud credHelper and
# cause HTTP 403 on push. This script logs in explicitly before docker push.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PROJECT="${GOOGLE_PROJECT_ID:-}"
REGION="${VERTEX_AI_REGION:-${GOOGLE_REGION:-us-central1}}"
REPO="${ARTIFACT_REGISTRY_REPO:-vertex}"
LOCAL_IMAGE="${DOCKER_IMAGE_NAME:-tds-favorita}:${DOCKER_TAG:-latest}"
REGISTRY_HOST="${REGION}-docker.pkg.dev"
REMOTE_IMAGE="${REGISTRY_HOST}/${PROJECT}/${REPO}/${LOCAL_IMAGE}"

if [[ -z "$PROJECT" ]]; then
  echo "GOOGLE_PROJECT_ID must be set in .env" >&2
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required. Install: https://cloud.google.com/sdk/docs/install" >&2
  exit 1
fi

ACTIVE_ACCOUNT="$(gcloud config get-value account 2>/dev/null || true)"
if [[ -z "$ACTIVE_ACCOUNT" ]]; then
  echo "No active gcloud account. Run: gcloud auth login" >&2
  exit 1
fi
echo "gcloud account: ${ACTIVE_ACCOUNT}"

echo "=== Configure Docker for ${REGISTRY_HOST} ==="
gcloud auth configure-docker "${REGISTRY_HOST}" --quiet

echo "=== Docker login (${REGISTRY_HOST}) ==="
# Avoid Docker Desktop credsStore overriding gcloud credHelper (403 on manifest push).
gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin "https://${REGISTRY_HOST}"

echo "=== Build ==="
docker compose build

echo "=== Tag ==="
echo "${LOCAL_IMAGE} -> ${REMOTE_IMAGE}"
docker tag "${LOCAL_IMAGE}" "${REMOTE_IMAGE}"

echo "=== Push ==="
if ! docker push "${REMOTE_IMAGE}"; then
  echo "" >&2
  echo "Push failed (often HTTP 403). Check:" >&2
  echo "  1. gcloud auth login  (user with roles/artifactregistry.writer or Owner)" >&2
  echo "  2. make vertex-gcp-setup  (repo exists in ${REGION})" >&2
  echo "  3. Re-run this script after: gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin https://${REGISTRY_HOST}" >&2
  exit 1
fi

echo ""
echo "OK. .env should contain:"
echo "  VERTEX_TRAINING_IMAGE=${REMOTE_IMAGE}"
