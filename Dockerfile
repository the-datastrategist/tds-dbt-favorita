FROM python:3.11-slim

# System environment settings
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set work directory
WORKDIR /app

# Install system-level dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (dev tools included for local Docker workflows)
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Copy project files
COPY . .

# Create necessary directories
RUN mkdir -p vertex/models/tmp dbt/target

# Default command (can be overridden)
ENTRYPOINT []
CMD ["bash"]
