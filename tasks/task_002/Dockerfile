# SWE-Universe Task Instance Dockerfile
# Repository: marshmallow-code/marshmallow
# Base Commit: d07bf5e3d218cd5ffa1fcd1dce411f7a5c88e256
# PR: #2892

# Layer 1: Base Image
FROM python:3.11-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Layer 2: Environment Setup
FROM base AS environment

WORKDIR /workspace

# Clone repository at base commit
RUN git clone https://github.com/marshmallow-code/marshmallow.git . && \
    git checkout d07bf5e3d218cd5ffa1fcd1dce411f7a5c88e256

# Install Python dependencies
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi
RUN if [ -f dev-requirements.txt ]; then pip install --no-cache-dir -r dev-requirements.txt; fi
RUN if [ -f setup.py ]; then pip install --no-cache-dir -e .; fi
RUN if [ -f pyproject.toml ]; then pip install --no-cache-dir -e .; fi

# Install common test dependencies
RUN pip install --no-cache-dir pytest pytest-cov pytest-xdist tox

# Layer 3: Instance Setup
FROM environment AS instance

# Set environment variables
ENV PYTHONPATH=/workspace
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy evaluation script
COPY eval_script.sh /eval_script.sh
RUN chmod +x /eval_script.sh

# Default command
CMD ["/bin/bash"]