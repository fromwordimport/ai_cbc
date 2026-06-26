#!/usr/bin/env bash
set -euo pipefail

: "${CF_WARP_ORG:?}"
: "${CF_WARP_CLIENT_ID:?}"
: "${CF_WARP_CLIENT_SECRET:?}"

if command -v warp-cli >/dev/null 2>&1; then
    echo "WARP 已安装"
else
    curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | \
      sudo gpg --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] \
      https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | \
      sudo tee /etc/apt/sources.list.d/cloudflare-client.list
    sudo apt update && sudo apt install -y cloudflare-warp
fi

sudo mkdir -p /var/lib/cloudflare-warp
sudo tee /var/lib/cloudflare-warp/mdm.xml > /dev/null <<EOF
<dict>
  <key>auth_client_id</key>
  <string>${CF_WARP_CLIENT_ID}</string>
  <key>auth_client_secret</key>
  <string>${CF_WARP_CLIENT_SECRET}</string>
  <key>organization</key>
  <string>${CF_WARP_ORG}</string>
  <key>auto_connect</key>
  <integer>1</integer>
  <key>service_mode</key>
  <string>warp</string>
  <key>onboarding</key>
  <false/>
</dict>
EOF

sudo systemctl enable --now warp-svc
sleep 2
warp-cli connect
echo "WARP 已启动"
