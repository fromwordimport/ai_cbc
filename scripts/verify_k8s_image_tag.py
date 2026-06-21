#!/usr/bin/env python3
"""Verify that kustomize build uses the expected image repository.

On Windows where kustomize is not available, falls back to static analysis
of the manifest files to confirm the expected image repository is referenced.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_REPO = "ghcr.io/fromwordimport/ai_cbc"
OLD_REPO = "ghcr.io/fromwordimport/aicbc"


def kustomize_available() -> bool:
    try:
        result = subprocess.run(
            ["kustomize", "version"],
            capture_output=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_overlay_with_kustomize(overlay: str) -> bool:
    result = subprocess.run(
        ["kustomize", "build", str(REPO_ROOT / "k8s" / "overlays" / overlay)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"FAIL: kustomize build {overlay} failed:\n{result.stderr}")
        return False
    if EXPECTED_REPO not in result.stdout:
        print(f"FAIL: overlay {overlay} does not use image {EXPECTED_REPO}")
        return False
    if OLD_REPO in result.stdout:
        print(f"FAIL: overlay {overlay} still uses old image {OLD_REPO}")
        return False
    print(f"OK: overlay {overlay} uses image {EXPECTED_REPO}")
    return True


def load_yaml(path: Path) -> list:
    with path.open("r", encoding="utf-8") as f:
        return list(yaml.safe_load_all(f))


def check_overlay_static(overlay: str) -> bool:
    """Static check: verify no old image references remain in base or overlay."""
    ok = True

    # Check base manifests for container images
    base_dir = REPO_ROOT / "k8s" / "base"
    for manifest_file in ["deployment.yaml", "worker-deployment.yaml", "beat-deployment.yaml"]:
        path = base_dir / manifest_file
        if not path.exists():
            print(f"FAIL: {path.relative_to(REPO_ROOT)} not found")
            ok = False
            continue
        docs = load_yaml(path)
        for doc in docs:
            if not doc:
                continue
            containers = doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
            for container in containers:
                image = container.get("image", "")
                if OLD_REPO in image:
                    print(f"FAIL: {manifest_file} still uses old image: {image}")
                    ok = False
                elif EXPECTED_REPO in image:
                    print(f"OK: {manifest_file} uses correct image: {image}")
                elif image:
                    print(f"WARN: {manifest_file} uses unexpected image: {image}")

    # Check kustomization files (base and overlay)
    for kust_file in [base_dir / "kustomization.yaml", REPO_ROOT / "k8s" / "overlays" / overlay / "kustomization.yaml"]:
        if not kust_file.exists():
            print(f"FAIL: {kust_file.relative_to(REPO_ROOT)} not found")
            ok = False
            continue
        docs = load_yaml(kust_file)
        for doc in docs:
            if not doc:
                continue
            images = doc.get("images", [])
            for image in images:
                name = image.get("name", "")
                if name == OLD_REPO:
                    print(f"FAIL: {kust_file.relative_to(REPO_ROOT)} still references old image name: {name}")
                    ok = False
                elif name == EXPECTED_REPO:
                    print(f"OK: {kust_file.relative_to(REPO_ROOT)} references correct image: {name}")

    # Check CD workflow files for correct kustomize edit command
    if overlay == "staging":
        workflow = REPO_ROOT / ".github" / "workflows" / "cd-staging.yml"
    else:
        workflow = REPO_ROOT / ".github" / "workflows" / "cd-production.yml"

    if workflow.exists():
        content = workflow.read_text(encoding="utf-8")
        if f"kustomize edit set image {EXPECTED_REPO}" in content:
            print(f"OK: {workflow.relative_to(REPO_ROOT)} uses correct kustomize edit target")
        elif "kustomize edit set image" in content:
            print(f"FAIL: {workflow.relative_to(REPO_ROOT)} kustomize edit target is wrong")
            ok = False
        else:
            print(f"WARN: {workflow.relative_to(REPO_ROOT)} has no kustomize edit set image command")
    else:
        print(f"WARN: {workflow.relative_to(REPO_ROOT)} not found")

    if ok:
        print(f"OK: overlay {overlay} static checks passed")
    else:
        print(f"FAIL: overlay {overlay} static checks failed")

    return ok


def check_overlay(overlay: str) -> bool:
    if kustomize_available():
        return check_overlay_with_kustomize(overlay)
    return check_overlay_static(overlay)


def main() -> int:
    ok = True
    for overlay in ("staging", "prod"):
        ok = check_overlay(overlay) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
