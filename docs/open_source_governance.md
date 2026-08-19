# Open-source governance

The repository is MIT licensed and maintainer-led. Issues establish user impact and acceptance
criteria; pull requests provide implementation and validation evidence. Maintainers decide scope,
contract changes, releases, and security handling based on documented platform goals.

Public API, warehouse, fixture, and configuration changes require compatibility review. Breaking
changes remain possible before 1.0 but must include migration notes and should preserve shims when
practical. Releases will use semantic versioning after the first public compatibility baseline.

Community participation is governed by the root contribution, conduct, security, and support
policies. Acceptance records under `docs/acceptance/` distinguish implemented repository behavior
from live cloud verification. A feature is not called shipped when required live acceptance is
still pending.

Maintainers must keep the public demo synthetic, use immutable dependency pins in CI, review
licenses for bundled assets, and prevent credentials or Terraform plan files from entering source
control.
