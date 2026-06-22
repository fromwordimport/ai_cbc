# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains **Kubernetes manifests** for AI_CBC. They are currently used for **CI static validation** (`validate-k8s` job) and **local kind/minikube testing**, not for the live production deployment. Production currently runs on Azure VM via `.github/workflows/cd-azure-b2ats.yml`.

## Layout

| Path | Purpose |
|------|---------|
| `base/kustomization.yaml` | Kustomize base: resources, common labels, base image reference |
| `base/configmap.yaml` | Non-sensitive configuration |
| `base/serviceaccount.yaml` | Dedicated ServiceAccounts for each component (SEC-011) |
| `base/secret.yaml` | Secret template with base64 placeholders (SEC-006) — kept as a reference but **not** included in the base kustomization resources; see Secret Management below |
| `base/deployment.yaml` | Main FastAPI API Deployment (3 replicas) |
| `base/worker-deployment.yaml` | Celery worker Deployment |
| `base/beat-deployment.yaml` | Celery beat scheduler Deployment |
| `base/statefulset.yaml` | Stateful workload (persistent data) |
| `base/redis.yaml` | Redis Deployment/Service |
| `base/network-policy.yaml` | Intra-namespace traffic restrictions |
| `base/ingress.yaml` | Ingress resource |
| `overlays/staging/` | Staging overlay (`namespace: aicbc-staging`) |
| `overlays/prod/` | Production overlay (`namespace: aicbc-prod`) |

## Conventions

- Use Kustomize overlays for environment-specific namespace and configuration.
- Standard labels: `app.kubernetes.io/name`, `app.kubernetes.io/component`, `app.kubernetes.io/version`.
- Security:
  - `runAsNonRoot: true` in pod security contexts.
  - `readOnlyRootFilesystem: true` with `emptyDir` volumes for `/tmp`.
  - `seccompProfile: RuntimeDefault` on all pods.
  - Dedicated `ServiceAccount` per component with `automountServiceAccountToken: false`.
  - `NetworkPolicy` restricts pod-to-pod traffic.
- Observability:
  - Prometheus scrape annotations on API/worker pods.
- Secrets are externalized via `secretKeyRef`:
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
  - `SECRET_KEY`

## Deployment

```bash
# Staging
kubectl apply -k k8s/overlays/staging

# Production
kubectl apply -k k8s/overlays/prod
```

The split CI/CD workflows in `../.github/workflows/ci.yml`, `../.github/workflows/cd-staging.yml`, and `../.github/workflows/cd-production.yml` handle quality gates, staging builds, and production deployments respectively.

## Secret Management

`secret.yaml` is a **template only** and is **not** included in the base `kustomization.yaml` resources list. It contains base64-encoded placeholder values that are intentionally invalid. Applying it directly would cause service startup failures.

Deployments that reference the secret via `secretKeyRef` expect the secret to be created separately **before** the overlay is applied. The base kustomization no longer applies `secret.yaml`, so CI/CD and manual deploys must ensure the real secret exists in the target namespace first.

See also the ESO example: [`base/external-secret.yaml.example`](base/external-secret.yaml.example).

### Recommended approaches (in order of preference)

1. **Sealed Secrets (kubeseal)** — encrypt secrets at rest, safe to commit to Git:
   ```bash
   kubectl create secret generic aicbc-secrets \
     --from-literal=anthropic-api-key=YOUR_KEY \
     --from-literal=openai-api-key=YOUR_KEY \
     --from-literal=secret-key=YOUR_SECRET \
     --dry-run=client -o yaml | kubeseal --format=yaml > sealed-secret.yaml
   kubectl apply -f sealed-secret.yaml
   ```

2. **External Secrets Operator (ESO)** — sync from AWS Secrets Manager, Azure Key Vault, or HashiCorp Vault:
   - See: https://external-secrets.io/latest/
   - Example manifest: `base/external-secret.yaml.example` (copy, customize remoteRef keys, and apply separately — it is **not** included in `kustomization.yaml` resources).

3. **CI/CD variable injection** — replace placeholders during deployment:
   ```bash
   sed -i "s/PLACEHOLDER_BASE64/$(echo -n $REAL_KEY | base64)/g" secret.yaml
   ```

### Secret template annotations

The template includes:
- `sealedsecrets.bitnami.com/managed: "false"` — marks it as not managed by Sealed Secrets controller
- `aicbc.internal/template: "true"` — identifies it as a template for audit purposes

## Cross-References

- `../docker/CLAUDE.md` — container build assets.
- `../docker-compose.yml` — local compose stack.
- `../.github/workflows/ci.yml` — continuous integration (quality gates, tests, frontend, K8s validation)
- `../.github/workflows/cd-staging.yml` — staging build and deployment (skipped if `KUBECONFIG_STAGING` is absent)
- `../.github/workflows/cd-azure-b2ats.yml` — current production deployment via SSH to Azure VM
- `../.github/workflows/security-scan.yml` — scheduled security scans
- `../.github/workflows/nightly.yml` — scheduled full tests and performance checks
- `../CLAUDE.md` — global repository guidance and team roles.
