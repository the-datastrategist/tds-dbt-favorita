FROM python:3.11-slim AS runtime

# System environment settings
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Install system-level dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Runtime dependencies only (Vertex Custom Jobs / production image)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p vertex/models/tmp dbt/target

# Local development: lint, test, and format tools on top of runtime
FROM runtime AS dev

COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Default image for docker compose / make (includes dev tools)
FROM dev

ENTRYPOINT []
CMD ["bash"]
