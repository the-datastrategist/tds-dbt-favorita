# Forecast webhook delivery acceptance — 2026-08-18

## Outcome

Signed outbound publication webhook delivery is implemented and locally accepted. Production
activation remains disabled until the receiver URL, shared signing secret, and operator rollout are
approved.

## Accepted behavior

- A successful publication produces a canonical JSON envelope with a stable publication event ID.
- Requests use HTTPS, HMAC-SHA256 verification headers, and the event ID as the idempotency key.
- A first attempt appends `pending` followed by `delivered` or `failed` delivery evidence.
- Retrying after failure advances the attempt number; a delivered or abandoned event is not sent
  again.
- Network, HTTP, and configuration failures do not roll back the immutable publication.
- Terraform injects the URL and signing secret from separate Secret Manager secrets.

## Evidence

The focused unit suite covers stable payload/signature generation, unsafe URL rejection, transport
failure redaction, successful state transitions, retry transitions, invalid configuration, and
terminal-state deduplication. Terraform validation covers development and production wiring. No
live external receiver was contacted during local acceptance.

## Production activation checklist

1. Create the URL and signing-secret Secret Manager secrets.
2. Have the receiver verify the raw-body signature, timestamp replay window, and event-ID
   deduplication before returning `2xx`.
3. Enable lifecycle mutations and `enable_publication_webhook` for the selected environment.
4. Publish a controlled test version, confirm `forecast_delivery_current` is `delivered`, and
   verify receiver-side processing by event ID.
5. Disable the webhook flag to stop future attempts if rollback is required; publication and
   delivery history remain immutable.
