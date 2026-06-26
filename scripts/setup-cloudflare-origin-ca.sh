#!/usr/bin/env bash
set -euo pipefail

SSL_DIR="/opt/aicbc/ssl"
mkdir -p "$SSL_DIR"

if [ ! -f "$SSL_DIR/cloudflare-origin-ca.pem" ] || [ ! -f "$SSL_DIR/cloudflare-origin-ca.key" ]; then
    echo "请从 Cloudflare Origin CA 下载证书和私钥，放到 $SSL_DIR"
    echo "期望文件: $SSL_DIR/cloudflare-origin-ca.pem 和 $SSL_DIR/cloudflare-origin-ca.key"
    exit 1
fi

chmod 644 "$SSL_DIR/cloudflare-origin-ca.pem"
chmod 600 "$SSL_DIR/cloudflare-origin-ca.key"
echo "Cloudflare Origin CA 证书权限已设置"
