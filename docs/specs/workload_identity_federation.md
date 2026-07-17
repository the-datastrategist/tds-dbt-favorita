{% docs spec_workload_identity_federation %}

# SPEC: Workload Identity Federation

**Status:** Proposed
**Roadmap reference:** [`iac.md`](../iac.md#security-checklist) security checklist — "Service account keys not in repo; prefer Workload Identity Federation"; [`vertex/ops/README.md`](../../vertex/ops/README.md#security-checklist) same item; [`client_rollout.md`](../client_rollout.md#post-rollout-weeks-58-optional) — "Workload Identity Federation | Replace SA keys"

---

## Summary

Every GCP-authenticated surface in this repo today — local Docker, Vertex Custom Jobs, and (in placeholder form) CI — is designed around a downloaded service-account JSON key file (`GOOGLE_APPLICATION_CREDENTIALS`). Key files are long-lived, easy to leak, and explicitly called out as a risk in this repo's own security checklist. This spec replaces key-file auth with Workload Identity Federation (WIF) in the two places it actually matters for a client engagement: **GitHub Actions CI** and **Vertex Custom Jobs**. Local developer auth keeps a lighter-weight path (`gcloud auth application-default login`) since a laptop isn't a "workload" WIF is designed for.

## Problem — current state

| Surface | Current auth | File |
|---------|-------------|------|
| Local Docker (`make vertex-*`) | Key file bind-mounted into container via `GOOGLE_APPLICATION_CREDENTIALS_CONTAINER` | [`docker-compose.yml`](../../docker-compose.yml) |
| CI (`.github/workflows/ci.yml`) | Placeholder key file (`echo '{}' > /tmp/ci-service-account.json`) — **not real**, but the pattern exists so any future job that talks to real GCP would need a real key stored as a GitHub secret | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) |
| Vertex Custom Jobs (`vertex.jobs.submit`) | The **local** `GOOGLE_APPLICATION_CREDENTIALS` path string is forwarded verbatim into the Custom Job container's env vars | [`vertex/jobs/gcp.py:167-169`](../../vertex/jobs/gcp.py#L167-L169) |

The third row is a latent bug worth fixing regardless of WIF: `creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS"); env.append({"name": ..., "value": creds})` propagates a **local filesystem path** (e.g. `/app/credentials/service-account-key.json`) into the Custom Job's container environment. That path doesn't exist inside the Vertex-managed container (the key file isn't baked into `VERTEX_TRAINING_IMAGE`, and Custom Jobs don't inherit the submitting machine's filesystem) — the Custom Job actually authenticates via its attached `service_account` (`VERTEX_PIPELINE_SERVICE_ACCOUNT`) and Google's metadata-server ADC, making this env var propagation dead weight at best, and a source of confusing `FileNotFoundError`s if any code path ever tries to open it inside the job.

## Goals

1. **CI**: authenticate to GCP (when CI needs to, e.g. the [Terraform spec](terraform_modules.md)'s live `plan`) via `google-github-actions/auth` + WIF pool/provider scoped to this repo — no long-lived secret in GitHub at all.
2. **Vertex Custom Jobs / PipelineJobs**: confirm (and document) that these already authenticate via the attached service account + ADC, not a key file; remove the dead `GOOGLE_APPLICATION_CREDENTIALS` propagation in `vertex/jobs/gcp.py`.
3. Update `iac.md` / `vertex/ops/README.md` security checklists from "prefer WIF" (aspirational) to "WIF configured for CI; Custom Jobs use attached SA + ADC" (factual), once done.

## Non-goals

- Removing key-file support for **local development**. `GOOGLE_APPLICATION_CREDENTIALS` + a downloaded key remains the simplest onboarding path for `make docker-bash` / `make vertex-train` on a laptop; WIF impersonation from a laptop (via `gcloud auth application-default login --impersonate-service-account`) is a nice-to-have, not a requirement, and adds setup friction for a repo whose audience includes prospective clients evaluating the demo.
- Cloud Scheduler → Cloud Run (`iac.md` Scheduling Pattern A) — once built, that Cloud Run service should run as an attached service account (no key file, no WIF needed — it's already a first-party GCP workload), which is a natural continuation of this spec but out of scope until Cloud Run trigger service exists.

## Design

### 1. CI: `google-github-actions/auth` + WIF

```yaml
# .github/workflows/ci.yml (new step, only for jobs that need real GCP — none exist yet)
permissions:
  contents: read
  id-token: write   # required for WIF

steps:
  - id: auth
    uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider
      service_account: ci-runner@PROJECT_ID.iam.gserviceaccount.com
```

Provisioned by the [Terraform spec](terraform_modules.md)'s `iam-vertex-sa` module (extended with a WIF pool/provider resource) or a small standalone `workload-identity` Terraform module:

```hcl
resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "github-pool"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id         = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository == '${var.github_repo}'"   # scope to this repo only
  oidc { issuer_uri = "https://token.actions.githubusercontent.com" }
}

resource "google_service_account_iam_member" "github_wif" {
  service_account_id = google_service_account.ci_runner.name
  role                = "roles/iam.workloadIdentityUser"
  member              = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}
```

The current placeholder credential (`echo '{}' > /tmp/ci-service-account.json`) stays exactly as-is for `dbt parse`/`dbt compile --no-introspect` — those steps deliberately avoid touching real GCP and shouldn't be given real credentials at all. WIF only matters the moment a CI job needs to *actually* call GCP (e.g. `terraform plan` against dev).

### 2. Vertex Custom Jobs — confirm ADC via attached SA, remove dead code

`vertex/jobs/submit.py` / `vertex/jobs/submit_pipeline.py` already set `service_account=settings.service_account` on the Custom Job / PipelineJob request (sourced from `VERTEX_PIPELINE_SERVICE_ACCOUNT`). Vertex AI's Custom Job runtime provides that service account's credentials via the instance metadata server automatically — no key file needed inside the job. Action: delete the dead propagation in `vertex/jobs/gcp.py`:

```python
# Remove — the submitting machine's local key-file path is meaningless inside
# the Custom Job container, which authenticates via the metadata server using
# the job's attached service_account (VERTEX_PIPELINE_SERVICE_ACCOUNT).
creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if creds:
    env.append({"name": "GOOGLE_APPLICATION_CREDENTIALS", "value": creds})
```

Add a regression test in `vertex/tests/` asserting the Custom Job env spec never contains a `GOOGLE_APPLICATION_CREDENTIALS` entry, so this doesn't silently come back.

### 3. Local submission identity (unaffected, but worth documenting explicitly)

The **machine that calls `vertex.jobs.submit`** (a developer's laptop, or eventually a CI runner) still needs credentials to make the `aiplatform.googleapis.com` API call that creates the Custom Job — that identity needs `roles/iam.serviceAccountUser` on `VERTEX_PIPELINE_SERVICE_ACCOUNT` to be allowed to "act as" it (this is exactly what `setup_vertex_service_account.sh`'s `CALLER_ACCOUNT` grant already does). WIF replaces *that* caller's key file too, once CI or another automated system is the one submitting jobs instead of a human running `make vertex-submit-train` locally.

## Rollout

1. Land the `vertex/jobs/gcp.py` dead-code removal independently — it's a small, safe cleanup with no WIF dependency.
2. Ship the WIF Terraform resources alongside (or as an extension of) the [Terraform spec](terraform_modules.md)'s `iam-vertex-sa` module.
3. Add the `google-github-actions/auth` step to CI **only when a real CI job needs it** (e.g. Terraform `plan` in dev) — don't add unused auth wiring speculatively.
4. Update security checklists in `iac.md` and `vertex/ops/README.md` to reflect the new state.

## Open questions

- Does the client's GCP org allow Workload Identity Pools (some highly locked-down orgs restrict pool creation to platform teams)? Confirm during Week 1 of `client_rollout.md` alongside the existing IAM-delay risk.
- Should local `make vertex-submit-train` eventually require impersonation-based ADC instead of a key file too, for parity with CI? Revisit once WIF-from-laptop tooling (`gcloud auth application-default login --impersonate-service-account`) is validated as low-friction enough for a demo repo's audience.

## Related documents

- [Specs index](README.md)
- [Terraform modules](terraform_modules.md) — where the WIF pool/provider resources live
- [IaC and GCP operations](../iac.md#security-checklist)
- `vertex/ops/README.md` — security checklist

{% enddocs %}
