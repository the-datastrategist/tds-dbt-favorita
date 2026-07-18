{% docs spec_workload_identity_federation %}

# SPEC: Workload Identity Federation

**Status:** Shipped
**Roadmap reference:** [`iac.md`](../iac.md#security-checklist) security checklist — "Service account keys not in repo; prefer Workload Identity Federation"; [`vertex/ops/README.md`](../../vertex/ops/README.md#security-checklist) same item; [`client_rollout.md`](../client_rollout.md#post-rollout-weeks-58-optional) — "Workload Identity Federation | Replace SA keys"

---

## Summary

Before this implementation, every GCP-authenticated surface in the repo—local Docker, Vertex
Custom Jobs, and the future authenticated CI path—was designed around a downloaded
service-account JSON key file (`GOOGLE_APPLICATION_CREDENTIALS`). This spec replaced automated
key-file authentication where it matters for a client engagement: **GitHub Actions CI** now uses
WIF, while **Vertex Custom Jobs** use their attached service account and metadata-server ADC.
Local development retains its documented key-file or human ADC paths.

## Problem — pre-implementation state

| Surface | Previous auth | File |
|---------|-------------|------|
| Local Docker (`make vertex-*`) | Key file bind-mounted into container via `GOOGLE_APPLICATION_CREDENTIALS_CONTAINER` | [`docker-compose.yml`](../../docker-compose.yml) |
| CI (`.github/workflows/ci.yml`) | Placeholder key file (`echo '{}' > /tmp/ci-service-account.json`) — **not real**, but the pattern exists so any future job that talks to real GCP would need a real key stored as a GitHub secret | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) |
| Vertex Custom Jobs (`vertex.jobs.submit`) | The **local** `GOOGLE_APPLICATION_CREDENTIALS` path string is forwarded verbatim into the Custom Job container's env vars | [`vertex/jobs/gcp.py:167-169`](../../vertex/jobs/gcp.py#L167-L169) |

The third row was also a latent bug: it propagated a **local filesystem path** into a managed
container where that path did not exist. The implementation removed that propagation; Custom Jobs
now unambiguously authenticate through the attached `VERTEX_PIPELINE_SERVICE_ACCOUNT` and
metadata-server ADC.

## Goals

1. **CI**: authenticate to GCP (when CI needs to, e.g. the [Terraform spec](terraform_modules.md)'s live `plan`) via `google-github-actions/auth` + WIF pool/provider scoped to this repo — no long-lived secret in GitHub at all.
2. **Vertex Custom Jobs / PipelineJobs**: confirm (and document) that these already authenticate via the attached service account + ADC, not a key file; remove the dead `GOOGLE_APPLICATION_CREDENTIALS` propagation in `vertex/jobs/gcp.py`.
3. Update `iac.md` / `vertex/ops/README.md` security checklists from "prefer WIF" (aspirational) to "WIF configured for CI; Custom Jobs use attached SA + ADC" (factual), once done.

## Non-goals

- Removing key-file support for **local development**. `GOOGLE_APPLICATION_CREDENTIALS` + a downloaded key remains the simplest onboarding path for `make docker-bash` / `make vertex-train` on a laptop; WIF impersonation from a laptop (via `gcloud auth application-default login --impersonate-service-account`) is a nice-to-have, not a requirement, and adds setup friction for a repo whose audience includes prospective clients evaluating the demo.
- Cloud Scheduler → Cloud Run (`iac.md` Scheduling Pattern A) — once built, that Cloud Run service should run as an attached service account (no key file, no WIF needed — it's already a first-party GCP workload), which is a natural continuation of this spec but out of scope until Cloud Run trigger service exists.

## Implementation notes

Repository changes and live acceptance are complete for the reference `tds-favorita` dev
environment. New client projects must repeat the documented bootstrap in
[`terraform/README.md`](../../terraform/README.md#keyless-github-actions-plan):

- **Done:** the dead-code removal in `vertex/jobs/gcp.py` — `worker_pool_spec` no longer
  propagates `GOOGLE_APPLICATION_CREDENTIALS` into the Custom Job container env. Added
  `vertex/tests/test_gcp.py` as the regression test called for above, asserting the env spec
  never contains that key and that the service account continues to flow through
  `settings.service_account` instead.
- **Done:** `vertex/ops/README.md` and `iac.md` security checklists updated to reflect this as
  factual (checked) rather than aspirational.
- **Done:** [Terraform modules](terraform_modules.md) shipped, including `iam-vertex-sa`, so the
  `google_iam_workload_identity_pool*` resources this spec calls for have a module to live in —
  removing that tooling blocker on steps 2–3.
- **Done:** `terraform/modules/github-wif` creates a dedicated CI service account, GitHub OIDC
  pool/provider restricted to the configured `owner/repository`, impersonation binding, read-only
  project access, and state-bucket-only lock access.
- **Done:** `.github/workflows/terraform.yml` authenticates the dev plan through
  `google-github-actions/auth`, requests `id-token: write` only on that job, rejects fork PRs, and
  retains a human-readable plan for seven days. It has no apply step.
- **Accepted 2026-07-18:** the live bootstrap verified the repository-scoped pool/provider,
  CI service account and IAM bindings, populated all protected GitHub `dev` variables, and
  produced a zero-change Terraform plan. GitHub Actions run
  [`29650216690`](https://github.com/the-datastrategist/tds-dbt-favorita/actions/runs/29650216690)
  successfully exchanged the GitHub OIDC token, described the live project, read the remote
  Terraform state, produced a clean plan, and completed dbt authentication and compilation using
  the dedicated `wif` ADC target without a service-account key.

## Design

### 1. CI: `google-github-actions/auth` + WIF

```yaml
# .github/workflows/terraform.yml (`plan-dev` job)
permissions:
  contents: read
  id-token: write   # required for WIF

steps:
  - id: auth
    uses: google-github-actions/auth@v3
    with:
      workload_identity_provider: projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider
      service_account: ci-runner@PROJECT_ID.iam.gserviceaccount.com
```

Provisioned by the standalone `terraform/modules/github-wif` module:

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
2. Ship the standalone WIF Terraform module and opt-in dev wiring. **Done.**
3. Add `google-github-actions/auth` to the real Terraform dev plan job. **Done.**
4. Bootstrap the module in the reference dev project and configure the protected GitHub `dev`
   environment. **Done 2026-07-18; repeat per client using `terraform/README.md`.**
5. Update security checklists in `iac.md` and `vertex/ops/README.md` so they state deployed facts
   rather than repository capability. **Done.**

## Open questions

- Does the client's GCP org allow Workload Identity Pools (some highly locked-down orgs restrict pool creation to platform teams)? Confirm during Week 1 of `client_rollout.md` alongside the existing IAM-delay risk.
- Should local `make vertex-submit-train` eventually require impersonation-based ADC instead of a key file too, for parity with CI? Revisit once WIF-from-laptop tooling (`gcloud auth application-default login --impersonate-service-account`) is validated as low-friction enough for a demo repo's audience.

## Related documents

- [Specs index](README.md)
- [Terraform modules](terraform_modules.md) — broader GCP provisioning design
- [IaC and GCP operations](../iac.md#security-checklist)
- `vertex/ops/README.md` — security checklist

{% enddocs %}
