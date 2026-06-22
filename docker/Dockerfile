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
    uv pip uninstall --system setuptools wheel || true && \
    rm -rf /usr/local/lib/python3.11/site-packages/setuptools* \
           /usr/local/lib/python3.11/site-packages/wheel* && \
    uv pip install --system --no-cache --upgrade setuptools wheel && \
    uv pip install --system --no-cache -e ".[analysis]" && \
    uv pip install --system --no-cache supervisor

# Defensive cleanup: transitive deps can still pull older setuptools/wheel
# versions into site-packages. Remove any remaining vulnerable dist-info dirs.
RUN python - <<'PY'
import re
import shutil
from pathlib import Path

def parse_version(v):
    return tuple(int(x) for x in v.split('.'))

def prune_distinfo(parent, prefixes, min_version):
    min_v = parse_version(min_version)
    for prefix in prefixes:
        for p in Path(parent).glob(f'{prefix}-*.dist-info'):
            m = re.match(re.escape(prefix) + r'-([0-9]+(?:\.[0-9]+)*)\.dist-info$', p.name)
            if not m:
                continue
            if parse_version(m.group(1)) < min_v:
                print(f'Removing {p}')
                shutil.rmtree(p)

site = Path('/usr/local/lib/python3.11/site-packages')
prune_distinfo(site, ['setuptools'], '82.0.1')
prune_distinfo(site, ['wheel'], '0.46.2')

vendor = site / 'setuptools' / '_vendor'
if vendor.exists():
    prune_distinfo(vendor, ['jaraco.context', 'jaraco_context'], '6.1.0')
    prune_distinfo(vendor, ['wheel'], '0.46.2')
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
