# AI_CBC API Service — Multi-stage Docker Build
# Stage 1: Builder — install dependencies
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Apply security updates and install build dependencies
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Note: uv.lock is gitignored, so install directly from pyproject.toml.
# Include [analysis] extras because Celery worker needs pandas/numpy/pymc.
COPY pyproject.toml ./
COPY src/ ./src/
ENV UV_NO_CACHE=1
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache -e ".[analysis]"

# Stage 2: Runtime — minimal image
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

# Apply security updates before installing runtime packages
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r aicbc && useradd -r -g aicbc aicbc

# Install supervisord for multi-process single container (Render free plan only supports one web service)
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=aicbc:aicbc src/ ./src/
COPY --chown=aicbc:aicbc configs/ ./configs/

# Copy supervisord configuration
COPY docker/supervisord-render.conf /etc/supervisor/conf.d/supervisord.conf

# Pre-compile bytecode to reduce cold-start import time on Render free tier
RUN python -m compileall -q /app/src /app/configs

# Remove write permissions for security
RUN chmod -R 555 /app/src /app/configs

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
