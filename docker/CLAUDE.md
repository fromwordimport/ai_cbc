# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains **container build assets** and local observability configuration for AI_CBC.

## Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage Python 3.11 image for the FastAPI backend |
| `nginx.conf` | Reverse proxy, TLS termination, rate limiting |
| `prometheus.yml` | Prometheus scrape configuration |
| `grafana/datasources/prometheus.yml` | Grafana datasource provisioning |
| `grafana/dashboards/aicbc-dashboard.json` | Pre-built Grafana dashboard |

## Dockerfile Conventions

- Multi-stage build: builder installs packages with `uv`; runtime copies installed site-packages and app code.
- Runs as non-root user `aicbc`.
- App code (`src/`, `configs/`) is copied with read-only permissions (`chmod -R 555`).
- Entry: `python -m uvicorn src.aicbc.main:app --host 0.0.0.0 --port 8000`.
- Includes a `HEALTHCHECK` on `/health`.

## Nginx Conventions

- Upstream `api_backend` points to the API container on port `8000`.
- Enforces TLS 1.2+, HTTP→HTTPS redirect, and ACME challenge support.
- Defines rate-limit zones: `api_limit`, `health_limit`, `conn_limit`.
- Emits structured logs with upstream timing.

## Local Full-Stack

The root `../docker-compose.yml` orchestrates: API, Celery worker, Celery beat, MongoDB, Redis, Nginx, Prometheus, Grafana.

```bash
cd ..
docker compose up --build
```

## Cross-References

- `../docker-compose.yml` — local compose stack.
- `../k8s/CLAUDE.md` — Kubernetes production deployment.
- `../src/CLAUDE.md` — backend source conventions.
- `../docs/CI-CD流水线设计.md` — CI/CD design.
