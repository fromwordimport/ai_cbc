# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains **container build assets** and local observability configuration for AI_CBC.

## Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage Python 3.11 image for the FastAPI backend |
| `nginx.conf` | Reverse proxy, TLS termination, rate limiting |
| `nginx.azure-b2ats.conf` | B2ats v2 生产环境 Nginx 配置 |
| `prometheus.yml` | Prometheus scrape configuration |
| `grafana/datasources/prometheus.yml` | Grafana datasource provisioning |
| `grafana/dashboards/aicbc-dashboard.json` | Pre-built Grafana dashboard |
| `supervisord-b2ats.conf` | 单 VM 回退：同时运行 uvicorn + Celery worker |
| `supervisord-api.conf` | 主 VM（B2ats）：仅运行 uvicorn |
| `supervisord-worker.conf` | Worker VM（ARM）：仅运行 Celery worker |

## Dockerfile Conventions

- Multi-stage build: builder installs packages with `uv`; runtime copies installed site-packages and app code.
- Runs as non-root user `aicbc`.
- App code (`src/`, `configs/`) is copied with read-only permissions (`chmod -R 555`).
- Entry: `python -m uvicorn src.aicbc.main:app --host 0.0.0.0 --port 8000`.
- Includes a `HEALTHCHECK` on `/health`.
- Security hardening: builder and runtime stages both run a version-based cleanup script that removes vulnerable `setuptools`, `wheel`, and vendored `jaraco.context` dist-info directories below safe versions (`setuptools>=82.0.1`, `wheel>=0.46.2`, `jaraco.context>=6.1.0`). This keeps the image clean of HIGH/CRITICAL CVEs reported by Trivy.

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

## Azure B2ats v2 双机部署

- `../docker-compose.azure-b2ats.yml`：主 VM 栈（API + MongoDB + Redis + nginx）。
- `../docker-compose.azure-worker.yml`：Worker VM 栈（仅 Celery worker）。
- `supervisord-api.conf` 与 `supervisord-worker.conf` 分别挂载到对应容器。
- 镜像需同时支持 `linux/amd64`（主 VM）与 `linux/arm64`（worker VM）。

## Cross-References

- `../docker-compose.yml` — local compose stack.
- `../docker-compose.azure-b2ats.yml` — Azure B2ats v2 production stack.
- `../k8s/CLAUDE.md` — Kubernetes manifests, kept for CI validation (`validate-k8s`) and local kind/minikube testing only.
- `../src/CLAUDE.md` — backend source conventions.
- `../docs/CI-CD流水线设计.md` — CI/CD design.
- `../.github/workflows/cd-azure-b2ats.yml` — current production deployment workflow.
- `../CLAUDE.md` — global repository guidance and team roles.
