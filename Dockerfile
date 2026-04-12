# Simplified single-stage Dockerfile for OpenEnv code review environment
FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl git && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
RUN pip install --no-cache-dir openenv-core uvicorn

# Copy project files
COPY . /app/env

WORKDIR /app/env

# Install project deps if pyproject.toml exists
RUN pip install --no-cache-dir -e . 2>/dev/null || true

# Set PYTHONPATH so imports work
ENV PYTHONPATH="/app/env:$PYTHONPATH"

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Run the FastAPI server
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]