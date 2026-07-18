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

CALLER_DOCKER_TAG="${DOCKER_TAG:-}"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
if [[ -n "${CALLER_DOCKER_TAG}" ]]; then
  DOCKER_TAG="${CALLER_DOCKER_TAG}"
fi

PROJECT="${GOOGLE_PROJECT_ID:-}"
REGION="${VERTEX_AI_REGION:-${GOOGLE_REGION:-us-central1}}"
REPO="${ARTIFACT_REGISTRY_REPO:-vertex}"
IMAGE_NAME="${DOCKER_IMAGE_NAME:-tds-favorita}"
GIT_SHA="$(git rev-parse --verify HEAD)"
IMAGE_TAG="${DOCKER_TAG:-${GIT_SHA}}"
if [[ "${IMAGE_TAG}" == "latest" ]]; then
  echo "Refusing mutable DOCKER_TAG=latest; unset DOCKER_TAG to use the Git SHA." >&2
  exit 1
fi
REGISTRY_HOST="${REGION}-docker.pkg.dev"
REMOTE_IMAGE="${REGISTRY_HOST}/${PROJECT}/${REPO}/${IMAGE_NAME}:${IMAGE_TAG}"

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

echo "=== Build and push immutable release image ==="
BUILDER_NAME="${DOCKER_BUILDX_BUILDER:-tds-favorita-release}"
TARGET_PLATFORM="${DOCKER_TARGET_PLATFORM:-linux/amd64}"
if ! docker buildx inspect "${BUILDER_NAME}" >/dev/null 2>&1; then
  docker buildx create \
    --name "${BUILDER_NAME}" \
    --driver docker-container \
    --use >/dev/null
else
  docker buildx use "${BUILDER_NAME}"
fi
docker buildx inspect --bootstrap "${BUILDER_NAME}" >/dev/null

if ! docker buildx build \
  --builder "${BUILDER_NAME}" \
  --platform "${TARGET_PLATFORM}" \
  --target production \
  --tag "${REMOTE_IMAGE}" \
  --label "org.opencontainers.image.revision=${GIT_SHA}" \
  --provenance=mode=max \
  --sbom=true \
  --push \
  .; then
  echo "" >&2
  echo "Push failed (often HTTP 403). Check:" >&2
  echo "  1. gcloud auth login  (user with roles/artifactregistry.writer or Owner)" >&2
  echo "  2. make vertex-gcp-setup  (repo exists in ${REGION})" >&2
  echo "  3. Ensure Docker Buildx is installed and rerun this script" >&2
  exit 1
fi

DIGEST="$(
  docker buildx imagetools inspect "${REMOTE_IMAGE}" --format '{{json .Manifest}}' \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["digest"])'
)"
if [[ ! "${DIGEST}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "Could not resolve an immutable digest for ${REMOTE_IMAGE}: ${DIGEST}" >&2
  exit 1
fi
IMMUTABLE_IMAGE="${REGISTRY_HOST}/${PROJECT}/${REPO}/${IMAGE_NAME}@${DIGEST}"

echo ""
echo "OK. .env should contain:"
echo "  VERTEX_TRAINING_IMAGE=${IMMUTABLE_IMAGE}"
