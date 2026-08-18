# Monitoring Slack activation — 2026-08-17

## Implemented

- Created the private Slack channel `#forecasting-ops` (`C0BQVUZ15PU`).
- Confirmed channel access with a clearly labeled connector smoke-test message; this does not count
  as production webhook acceptance.
- Added a first-class `slack` alert destination that formats severity, policy, reason, resource,
  signal, and observation time for an incoming webhook.
- Routed all configured ticket/page forecast policies to the Slack destination.
- Enabled Secret Manager in `tds-favorita` and created the empty `forecast-slack-webhook` secret
  container. No credential value was written to the repository or Terraform state.
- Updated the monitoring runner to inject the latest secret version as
  `FORECAST_SLACK_WEBHOOK_URL` and grant `secretAccessor` only to its service account.
- Added matching dev/prod Terraform variables and operator documentation.

## Validation

- Focused monitoring alert tests passed (`9 passed`), including Slack payload formatting and
  environment indirection.
- The full unit suite passed (`380 passed`, `7 deselected`) with 76.43% coverage.
- Terraform formatting passed.
- Fresh temporary initialization and validation passed for both dev and prod configurations with
  Google provider `7.44.0`.

## Pending live acceptance

The Slack connector can create and post to channels but cannot create or reveal an incoming
webhook. A Slack administrator must create/authorize the webhook for `#forecasting-ops`, then add
its URL as the first secret version using the stdin workflow in `docs/monitoring_and_slos.md`.
After that, build and push the committed image, apply the reviewed Terraform plan, inject one
controlled alert, witness exactly one Slack delivery, clear the condition, and verify recovery.

Until those steps are complete, the monitoring specification remains at 99% rather than shipped.
