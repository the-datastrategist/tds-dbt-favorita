# Security policy

Do not open public issues for suspected vulnerabilities or exposed credentials. Report them through
GitHub private vulnerability reporting for this repository. Include the affected version or commit,
reproduction steps, impact, and any suggested mitigation. Do not access data beyond what is needed
to demonstrate the issue.

The latest default branch receives security fixes. Public GitHub Pages assets are synthetic and
must never be treated as an authentication boundary. Production ForecastLab deployments require
IAP or equivalent authentication, API-side role checks, least-privilege service accounts, and
Secret Manager for webhook credentials.
