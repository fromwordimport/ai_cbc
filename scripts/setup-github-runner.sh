#!/usr/bin/env bash
set -euo pipefail

REPO="${GITHUB_REPO:-fromwordimport/ai_cbc}"
TOKEN="${GITHUB_RUNNER_TOKEN:?环境变量 GITHUB_RUNNER_TOKEN 未设置}"
RUNNER_NAME="${GITHUB_RUNNER_NAME:-azure-b2ats}"

RUNNER_DIR="/opt/github-runner"
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

LATEST=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest | grep tag_name | cut -d\" -f4)
VERSION="${LATEST#v}"
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)  RUNNER_ARCH="x64" ;;
    aarch64) RUNNER_ARCH="arm64" ;;
    *) echo "不支持的架构: $ARCH"; exit 1 ;;
esac

curl -fsSL -o actions-runner-linux-$RUNNER_ARCH-$VERSION.tar.gz \
  "https://github.com/actions/runner/releases/download/$LATEST/actions-runner-linux-$RUNNER_ARCH-$VERSION.tar.gz"

tar xzf actions-runner-linux-$RUNNER_ARCH-$VERSION.tar.gz
./config.sh --url "https://github.com/$REPO" --token "$TOKEN" --name "$RUNNER_NAME" --labels "self-hosted,azure-b2ats" --unattended
sudo ./svc.sh install
sudo ./svc.sh start

echo "GitHub runner 已安装并启动"
