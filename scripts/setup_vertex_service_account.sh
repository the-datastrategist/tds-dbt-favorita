#!/usr/bin/env bash
# One-time GCP setup for the Vertex pipeline service account (run with a user or
# admin account, not the Cursor/CI SA — it needs iam.serviceAccounts.create and
# resourcemanager.projects.setIamPolicy).
#
#   gcloud auth login
#   bash scripts/setup_vertex_service_account.sh
#
# Creates VERTEX_PIPELINE_SERVICE_ACCOUNT (.env; default sa-vertex-ml@$GOOGLE_PROJECT_ID)
# with the least-privilege roles from vertex/ops/README.md, then grants
# roles/iam.serviceAccountUser on it to the identity that submits Custom Jobs/PipelineJobs
# (GOOGLE_APPLICATION_CREDENTIALS, or CALLER_ACCOUNT override) so submission is allowed
# to "act as" it.

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
SA_EMAIL="${VERTEX_PIPELINE_SERVICE_ACCOUNT:-sa-vertex-ml@${PROJECT}.iam.gserviceaccount.com}"
SA_ID="${SA_EMAIL%%@*}"

# Identity that will submit Custom Jobs / PipelineJobs and needs to "act as" $SA_EMAIL.
# Defaults to the client_email in GOOGLE_APPLICATION_CREDENTIALS; override with CALLER_ACCOUNT=....
CALLER_ACCOUNT="${CALLER_ACCOUNT:-}"
if [[ -z "$CALLER_ACCOUNT" && -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" && -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]]; then
  CALLER_ACCOUNT="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('client_email',''))" "${GOOGLE_APPLICATION_CREDENTIALS}")"
fi
CALLER_ACCOUNT="${CALLER_ACCOUNT:?Set CALLER_ACCOUNT=user-or-sa-email, or set GOOGLE_APPLICATION_CREDENTIALS to a valid key file}"

echo "Project:        ${PROJECT}"
echo "Service account: ${SA_EMAIL}"
echo "Caller (actAs):  ${CALLER_ACCOUNT}"
echo ""

echo "=== Create service account (idempotent) ==="
if gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT}" >/dev/null 2>&1; then
  echo "${SA_EMAIL} already exists."
else
  gcloud iam service-accounts create "${SA_ID}" \
    --project="${PROJECT}" \
    --display-name="Vertex AI pipeline/training jobs"
fi

echo "=== Grant least-privilege roles (vertex/ops/README.md) ==="
for ROLE in \
  roles/aiplatform.user \
  roles/storage.objectAdmin \
  roles/bigquery.dataEditor \
  roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --condition=None \
    --quiet >/dev/null
  echo "  granted ${ROLE}"
done

echo "=== Allow ${CALLER_ACCOUNT} to act as ${SA_EMAIL} ==="
CALLER_MEMBER="serviceAccount:${CALLER_ACCOUNT}"
if [[ "${CALLER_ACCOUNT}" != *.gserviceaccount.com ]]; then
  CALLER_MEMBER="user:${CALLER_ACCOUNT}"
fi
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --project="${PROJECT}" \
  --member="${CALLER_MEMBER}" \
  --role="roles/iam.serviceAccountUser" \
  --quiet >/dev/null
echo "  granted roles/iam.serviceAccountUser to ${CALLER_MEMBER}"

echo ""
echo "=== Done ==="
echo "Ensure .env has:"
echo "  VERTEX_PIPELINE_SERVICE_ACCOUNT=${SA_EMAIL}"
echo "Then retry: make vertex-submit-train"
