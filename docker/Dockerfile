# AI_CBC API Service — Multi-stage Docker Build
# Stage 1: Builder — install dependencies
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Apply security updates and install build dependencies
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get dist-upgrade -y && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Note: uv.lock is gitignored, so install directly from pyproject.toml.
# Include [analysis] extras because Celery worker needs pandas/numpy/pymc.
COPY pyproject.toml ./
COPY src/ ./src/
ENV UV_NO_CACHE=1
# Use uv for all package installs to avoid stale setuptools/wheel vendor
# dist-info left behind by mixing pip upgrade with uv installs.
RUN pip install --no-cache-dir --upgrade uv && \
    uv pip install --system --no-cache --force-reinstall --upgrade setuptools wheel && \
    uv pip install --system --no-cache -e ".[analysis]" && \
    uv pip install --system --no-cache supervisor

# Remove stale setuptools vendor dist-info directories that uv may leave behind
# after force-reinstalling setuptools (older vendored jaraco.context/wheel).
RUN python - <<'PY'
import shutil
from pathlib import Path
base = Path('/usr/local/lib/python3.11/site-packages/setuptools/_vendor')
for stale in [
    base / 'jaraco.context-5.3.0.dist-info',
    base / 'wheel-0.45.1.dist-info',
]:
    if stale.exists():
        shutil.rmtree(stale)
        print(f'Removed {stale}')
PY

# Stage 2: Runtime — minimal image
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

# Apply security updates before installing runtime packages
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get dist-upgrade -y && \
    apt-get install -y --no-install-recommends \
    libexpat1 \
    libssl3 \
    openssl \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r aicbc && useradd -r -g aicbc aicbc

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

CMD ["/usr/local/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
