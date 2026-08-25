# ForecastLab controlled mutation activation — 2026-08-23

## Result

**Blocked safely before activation.** The read-only production service remained unchanged. No
lifecycle role, mutation flag, publication-webhook flag, or BigQuery write permission was enabled.

## Preflight evidence

- Read-only ForecastLab acceptance was already complete.
- The publication signing-secret and Slack webhook secret each had an enabled version.
- Both publication URL versions were disabled at the start of preflight.
- URL version 2 was enabled only long enough to inspect non-secret URL metadata. It was nonempty
  but was not a URL: its payload began with the shell prompt text
  `read -rs "PUBLICATION_WEBHOOK_URL` and had no HTTPS scheme or hostname.
- URL version 2 was immediately disabled again.
- Only one named IAP identity is currently configured, so independent planner, approver, and
  publisher denial tests cannot yet be witnessed with separate people.

## Required remediation

1. Add a new publication URL secret version containing only the approved HTTPS receiver URL.
2. Confirm that the receiver validates the HMAC signature, replay window, and event ID before it
   returns a successful response.
3. Add separate named test identities for planner, approver, and publisher if separation-of-duty
   denial evidence is required.
4. Re-run the controlled plan, enable mutations and the webhook for the bounded exercise, capture
   append-only audit and delivery evidence, and restore read-only mode.

This record is a failed-closed preflight, not production mutation or webhook acceptance.
