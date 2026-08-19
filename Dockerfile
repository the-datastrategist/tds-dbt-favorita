# Pin the official multi-platform base image so production builds cannot drift silently.
FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS builder

# System environment settings
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Build native Python dependencies outside the final image.
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y \
    --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# XGBoost and other native wheels use the OpenMP runtime, but compilers and source-control
# clients stay in the builder/development stages.
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y \
    --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# Build frontends are unnecessary at runtime. Removing both the base-image and
# virtualenv copies also keeps their vendored packages out of vulnerability scans.
RUN /usr/local/bin/python -m pip uninstall --yes setuptools wheel \
    && /opt/venv/bin/python -m pip uninstall --yes setuptools wheel

COPY . .

# Resolve dbt packages while building so scheduled jobs do not depend on
# outbound package downloads at runtime. dbt renders the profile during deps,
# so supply a non-production placeholder project without authenticating.
RUN GOOGLE_PROJECT_ID=container-build dbt deps --project-dir dbt --profiles-dir dbt/profiles \
    && mkdir -p vertex/models/tmp dbt/target

# Production image: run Vertex workloads without root privileges.
FROM runtime AS production

RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && chown -R app:app /app

USER app

ENTRYPOINT []
CMD ["python", "-m", "vertex.jobs.run", "--help"]

# Local development: lint, test, and format tools on top of runtime. Compose explicitly
# selects this target because bind-mounted developer files need the host's normal workflow.
FROM runtime AS dev

USER root

RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

ENTRYPOINT []
CMD ["bash"]
