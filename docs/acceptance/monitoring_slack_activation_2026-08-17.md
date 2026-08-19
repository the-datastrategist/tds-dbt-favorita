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

## Live acceptance — 2026-08-18

- Added an enabled Secret Manager version for `forecast-slack-webhook`; the URL was never written
  to the repository or Terraform state.
- Applied the enabled monitoring runner and hourly UTC scheduler with zero Terraform destroys.
- Deployed the immutable Linux/AMD64 production image
  `sha256:cabf3fe04f4ab47d2107dcc7f50d416aa2b54cee05f7bbb82ce9c4a75282994c`.
- Corrected the production dbt target to use Cloud Run service-account ADC and made the image
  self-contained by resolving dbt packages at build time.
- Cloud Run execution `forecast-monitoring-evaluator-6mcz7` completed successfully. The selected
  monitoring build ran 136 resources/tests and the evaluator read every configured BigQuery
  signal.
- The hosted evaluator delivered three real policy alerts to private channel `#forecasting-ops`
  (`C0BQVUZ15PU`): two `missing_eligibility_evidence` alerts and one stale-publication alert.
- A separate, clearly labeled `controlled_slack_acceptance` event was routed through the same
  application code and webhook secret. Routing reported exactly one emitted event, and the exact
  message was witnessed in the channel with resource key `forecast-monitoring-evaluator-6mcz7`.

The Slack path is now live accepted. The alerts reflect the current static demonstration data and
should be remediated or explicitly acknowledged through the associated runbooks; they do not
invalidate notification delivery acceptance.
