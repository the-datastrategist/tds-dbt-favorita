# Contributing

Thank you for improving the forecasting platform. Start with the credential-free example:

```bash
make quickstart-local
```

For Python changes, install `requirements-dev.txt` and run `make check` plus the relevant tests.
For ForecastLab changes, run `npm ci`, `npm run validate`, and the affected Playwright suites from
`frontend/`. Terraform changes require `terraform fmt -check` and validation in both environments.

Keep pull requests focused, add regression evidence, update contracts and documentation when
behavior changes, and never commit credentials, client data, Terraform plans, or unsanitized
fixtures. New generic capabilities should expose typed extension boundaries rather than importing
Favorita-specific assumptions into platform modules.

By participating, you agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Security issues
must follow [SECURITY.md](SECURITY.md), not the public issue tracker.
