#!/usr/bin/env python3
"""Static validator for AI_CBC K8s manifests.

This script performs offline checks on the K8s manifests in `k8s/` and its
overlays. It does not require a cluster or kubectl/kustomize binaries, but it
also does not replace a real cluster deployment test.

Run with:
    uv run python scripts/validate_k8s_manifests.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
K8S_DIR = REPO_ROOT / "k8s"
BASE_DIR = K8S_DIR / "base"

ISSUES: list[tuple[str, str]] = []


def fail(category: str, message: str) -> None:
    ISSUES.append((category, message))


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return list(yaml.safe_load_all(f))


def validate_kustomization(base: Path) -> None:
    kustomization_path = base / "kustomization.yaml"
    if not kustomization_path.exists():
        fail("kustomize", f"missing {kustomization_path.relative_to(REPO_ROOT)}")
        return

    docs = load_yaml(kustomization_path)
    if not docs or not docs[0]:
        fail("kustomize", f"empty {kustomization_path.relative_to(REPO_ROOT)}")
        return

    kust = docs[0]
    resources = kust.get("resources", [])
    for resource in resources:
        resource_path = base / resource
        if not resource_path.exists():
            fail("kustomize", f"referenced resource missing: {resource_path.relative_to(REPO_ROOT)}")
        elif resource_path.is_dir() and not (resource_path / "kustomization.yaml").exists():
            fail("kustomize", f"referenced directory missing kustomization.yaml: {resource_path.relative_to(REPO_ROOT)}")

    images = kust.get("images", [])
    for image in images:
        if image.get("newTag") == "latest":
            fail("kustomize", f"{kustomization_path.relative_to(REPO_ROOT)} uses tag 'latest': {image.get('name')}")


def validate_security_context(doc: Any, source: str) -> None:
    spec = doc.get("spec", {}).get("template", {}).get("spec", {})
    pod_sc = spec.get("securityContext", {})

    if not pod_sc.get("runAsNonRoot"):
        fail("security", f"{source}: pod securityContext.runAsNonRoot != true")

    if pod_sc.get("seccompProfile", {}).get("type") != "RuntimeDefault":
        fail("security", f"{source}: pod securityContext.seccompProfile.type != RuntimeDefault")

    if spec.get("automountServiceAccountToken") is not False:
        fail("security", f"{source}: automountServiceAccountToken != false")

    if not spec.get("serviceAccountName"):
        fail("security", f"{source}: missing serviceAccountName")

    containers = spec.get("containers", [])
    for container in containers:
        cname = container.get("name", "unknown")
        csc = container.get("securityContext", {})

        if csc.get("allowPrivilegeEscalation") is not False:
            fail("security", f"{source}/{cname}: allowPrivilegeEscalation != false")

        drops = csc.get("capabilities", {}).get("drop", [])
        if "ALL" not in drops:
            fail("security", f"{source}/{cname}: capabilities.drop does not include ALL")

        # MongoDB needs a writable data directory via PVC; everything else
        # should run with a read-only root filesystem.
        if cname == "mongo":
            continue

        if csc.get("readOnlyRootFilesystem") is not True:
            fail("security", f"{source}/{cname}: readOnlyRootFilesystem != true")

        # Image immutability
        image = container.get("image", "")
        if ":latest" in image:
            fail("security", f"{source}/{cname}: image uses 'latest' tag: {image}")

        if container.get("imagePullPolicy") == "Always":
            fail("security", f"{source}/{cname}: imagePullPolicy == Always")


def validate_secret(doc: Any, source: str) -> None:
    if "stringData" in doc:
        fail("security", f"{source}: Secret uses stringData (should use data)")

    data = doc.get("data", {})
    for key, value in data.items():
        if not isinstance(value, str):
            continue
        # Base64 encoded placeholder check for common dummy values
        decoded = value
        import base64

        try:
            decoded = base64.b64decode(value.encode()).decode("utf-8")
        except Exception:
            pass
        if "REPLACE_WITH" in decoded or decoded == "":
            fail("secret", f"{source}: {key} still contains placeholder value")


def validate_network_policy(docs: list[Any]) -> None:
    names = {
        doc.get("metadata", {}).get("name")
        for doc in docs
        if doc and doc.get("kind") == "NetworkPolicy"
    }
    required = {"default-deny-all", "allow-ingress-to-api", "deny-ingress-worker-beat", "allow-dns"}
    missing = required - names
    if missing:
        fail("network", f"missing recommended NetworkPolicy resources: {missing}")


def validate_overlay(overlay_dir: Path) -> None:
    validate_kustomization(overlay_dir)
    for doc in load_yaml(overlay_dir / "kustomization.yaml"):
        if doc and doc.get("namespace"):
            namespace = doc.get("namespace")
            if "example" in namespace or not namespace:
                fail("overlay", f"{overlay_dir.name}: suspicious namespace '{namespace}'")


def main() -> int:
    print("== AI_CBC K8s Manifest Static Validator ==\n")

    # Base kustomization
    validate_kustomization(BASE_DIR)

    # Overlays
    for overlay in (K8S_DIR / "overlays").iterdir():
        if overlay.is_dir():
            validate_overlay(overlay)

    # Load all base manifests
    kust_docs = load_yaml(BASE_DIR / "kustomization.yaml")
    if kust_docs and kust_docs[0]:
        resources = kust_docs[0].get("resources", [])
    else:
        resources = []

    all_docs: list[Any] = []
    for resource in resources:
        path = BASE_DIR / resource
        if path.exists():
            all_docs.extend(load_yaml(path))

    for doc in all_docs:
        if not doc:
            continue
        kind = doc.get("kind", "Unknown")
        name = doc.get("metadata", {}).get("name", "unknown")
        source = f"{kind}/{name}"

        if kind in ("Deployment", "StatefulSet"):
            validate_security_context(doc, source)

        if kind == "Secret":
            validate_secret(doc, source)

    validate_network_policy(all_docs)

    # Summary
    categories: dict[str, list[str]] = {}
    for category, message in ISSUES:
        categories.setdefault(category, []).append(message)

    if not ISSUES:
        print("No issues found. Static validation passed.")
        return 0

    print(f"Found {len(ISSUES)} issue(s):\n")
    for category in sorted(categories):
        print(f"[{category}]")
        for message in categories[category]:
            print(f"  - {message}")
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
