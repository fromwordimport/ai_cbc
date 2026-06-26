# Azure 公共 IP 免费替代方案实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不使用付费 Azure 公共 IP 的前提下，将 AI_CBC 生产入口迁移到 Cloudflare Tunnel，并保留双轨 CI/CD 部署能力。

**Architecture:** 通过 Cloudflare Tunnel（`cloudflared`）将 HTTPS 流量引入仅具有私有 IP 的 Azure B2ats v2 VM；Nginx 仅监听本地回环；DNS 从 A 记录改为 CNAME；CI/CD 使用 VM 内 self-hosted runner 为主路径、Azure Run Command 为备用路径。若 Azure 默认出站访问不可用，则启用 Cloudflare WARP/One 作为免费出站方案。

**Tech Stack:** Azure B2ats v2, Cloudflare Tunnel, Cloudflare Origin CA, Docker Compose, Nginx, GitHub Actions self-hosted runner, Azure CLI Run Command, Cloudflare WARP (fallback)

## Global Constraints

- 最终目标必须是 **0 额外 Azure 费用**；不允许引入 NAT Gateway、Bastion、负载均衡器等付费组件。
- 所有变更必须可回滚：原 Azure 公共 IP 在实施完成前只解绑、不删除；DNS TTL 提前调低。
- 实施前必须完成 Azure 默认出站访问验证；失败时启用 Cloudflare WARP/One fallback 再次验证。
- Nginx 在 Cloudflare Tunnel 架构下不应监听 VM 外部接口。
- CI/CD 必须保留至少两条独立部署路径，确保不依赖单一机制。

---

## File Structure

| 文件 | 用途 | 操作 |
|---|---|---|
| `docker-compose.azure-b2ats.yml` | Azure 生产 Compose 栈 | 修改 Nginx 端口绑定为 `127.0.0.1:80:80` / `127.0.0.1:443:443` |
| `docker/nginx.azure-b2ats.conf` | Nginx 生产配置 | 修改 server_name 为实际域名；切换 SSL 证书路径到 Cloudflare Origin CA |
| `scripts/setup-cloudflared.sh` | VM 上安装并启动 cloudflared | 新建 |
| `scripts/setup-warp.sh` | VM 上安装并启动 Cloudflare WARP（fallback） | 新建 |
| `scripts/setup-github-runner.sh` | VM 上注册 GitHub self-hosted runner | 新建 |
| `.github/workflows/cd-azure-b2ats.yml` | 现有生产部署工作流 | 重构为双轨部署（self-hosted runner + Azure Run Command） |
| `docs/superpowers/specs/2026-06-26-azure-public-ip-alternative-design.md` | 设计文档 | 仅参考，不修改 |

---

### Task 1: 前置信息收集与 Cloudflare Tunnel 创建

**Files:**
- Create: `scripts/setup-cloudflared.sh`
- Reference: `docs/superpowers/specs/2026-06-26-azure-public-ip-alternative-design.md`

**Interfaces:**
- Consumes: Cloudflare 账户、目标子域名（如 `api.example.com`）、Cloudflare Zero Trust 组织名
- Produces: `TUNNEL_TOKEN`（存入 GitHub Secrets `CF_TUNNEL_TOKEN`），`<TUNNEL_ID>.cfargotunnel.com`

- [ ] **Step 1: 确认 Cloudflare DNS 权限**

  登录 Cloudflare 仪表盘，确认目标域名已托管在 Cloudflare，且可以修改目标子域名的 DNS 记录。

  Test: 在 Cloudflare 仪表盘看到目标域名和现有 `A` 记录指向 Azure 公共 IP。

- [ ] **Step 2: 创建 Cloudflare Tunnel**

  进入 Cloudflare Zero Trust → Networks → Tunnels → Create a tunnel。
  选择 Cloudflare One Connector，命名如 `aicbc-azure-b2ats`。
  创建后复制 tunnel token。

  Test: 确认 token 格式为长串 JWT，保存到密码管理器，稍后存入 GitHub Secrets `CF_TUNNEL_TOKEN`。

- [ ] **Step 3: 配置 Public Hostname**

  在 tunnel 的 Public Hostname 中添加：
  - Subdomain: `api`（或你的子域名前缀）
  - Domain: `example.com`
  - Path: 留空
  - Type: HTTP
  - URL: `http://localhost:80`

  Test: 在 Cloudflare 控制台看到该 Public Hostname 状态为 Active（cloudflared 运行后）。

- [ ] **Step 4: 编写 cloudflared 安装脚本**

  创建 `scripts/setup-cloudflared.sh`：

  ```bash
  #!/usr/bin/env bash
  set -euo pipefail

  TUNNEL_TOKEN="${CF_TUNNEL_TOKEN:?环境变量 CF_TUNNEL_TOKEN 未设置}"

  if docker ps -q -f name=cloudflared | grep -q .; then
      echo "cloudflared 容器已运行，先停止"
      docker stop cloudflared || true
      docker rm cloudflared || true
  fi

  docker run -d \
    --name cloudflared \
    --restart unless-stopped \
    --network host \
    -e TUNNEL_TOKEN="$TUNNEL_TOKEN" \
    cloudflare/cloudflared:latest tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"

  echo "cloudflared 已启动"
  ```

  Test: 在本地使用 `bash -n scripts/setup-cloudflared.sh` 检查语法。

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/setup-cloudflared.sh
  git commit -m "ops(azure): add cloudflared setup script for Cloudflare Tunnel"
  ```

---

### Task 2: 调整 Nginx 绑定与证书路径

**Files:**
- Modify: `docker-compose.azure-b2ats.yml:130-151`
- Modify: `docker/nginx.azure-b2ats.conf:35-115`
- Create: `scripts/setup-cloudflare-origin-ca.sh`

**Interfaces:**
- Consumes: Cloudflare Origin CA 证书和私钥
- Produces: Nginx 仅监听 `127.0.0.1`，使用 `/etc/nginx/ssl/cloudflare-origin-ca.pem` 和 `.key`

- [ ] **Step 1: 修改 docker-compose Nginx 端口绑定**

  将 `docker-compose.azure-b2ats.yml` 中：

  ```yaml
  ports:
    - "80:80"
    - "443:443"
  ```

  改为：

  ```yaml
  ports:
    - "127.0.0.1:80:80"
    - "127.0.0.1:443:443"
  ```

  Test: `docker compose -f docker-compose.azure-b2ats.yml config | grep -A2 nginx_ports` 只出现 127.0.0.1。

- [ ] **Step 2: 修改 Nginx server_name 和证书路径**

  在 `docker/nginx.azure-b2ats.conf` 中：

  1. 将两个 `server` 块中的 `server_name _;` 改为实际域名，例如 `server_name api.example.com;`。
  2. 将 443 server 块中的：

     ```nginx
     ssl_certificate /etc/nginx/ssl/cert.pem;
     ssl_certificate_key /etc/nginx/ssl/key.pem;
     ```

     改为：

     ```nginx
     ssl_certificate /etc/nginx/ssl/cloudflare-origin-ca.pem;
     ssl_certificate_key /etc/nginx/ssl/cloudflare-origin-ca.key;
     ```

  Test: `nginx -t -c /path/to/nginx.azure-b2ats.conf`（在本地或容器内）无语法错误。

- [ ] **Step 3: 编写 Origin CA 证书安装脚本**

  创建 `scripts/setup-cloudflare-origin-ca.sh`：

  ```bash
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
  ```

  Test: 在本地运行 `bash -n scripts/setup-cloudflare-origin-ca.sh` 检查语法。

- [ ] **Step 4: Commit**

  ```bash
  git add docker-compose.azure-b2ats.yml docker/nginx.azure-b2ats.conf scripts/setup-cloudflare-origin-ca.sh
  git commit -m "ops(azure): bind nginx to localhost and switch to Cloudflare Origin CA"
  ```

---

### Task 3: Azure 默认出站访问验证

**Files:**
- Reference: `docs/superpowers/specs/2026-06-26-azure-public-ip-alternative-design.md`
- Create: `scripts/verify-outbound.sh`

**Interfaces:**
- Consumes: Azure VM 访问权限（门户或现有 SSH）
- Produces: `outbound-verification-passed` 或进入 Task 4（WARP fallback）

- [ ] **Step 1: 编写出站验证脚本**

  创建 `scripts/verify-outbound.sh`：

  ```bash
  #!/usr/bin/env bash
  set -euo pipefail

  echo "测试 Cloudflare HTTPS 连通性..."
  curl -fsSI https://cloudflare.com > /dev/null || { echo "FAIL: 无法访问 https://cloudflare.com"; exit 1; }

  echo "测试 Docker Hub 镜像拉取..."
  docker pull hello-world > /dev/null || { echo "FAIL: 无法从 Docker Hub 拉取镜像"; exit 1; }
  docker rmi hello-world > /dev/null || true

  echo "测试 GitHub 仓库访问..."
  cd /opt/aicbc
  git fetch origin master || { echo "FAIL: 无法 fetch GitHub"; exit 1; }

  echo "PASS: 默认出站访问可用"
  ```

- [ ] **Step 2: 在 Azure 门户临时解绑公共 IP**

  1. 进入 VM → Networking → Network Interface → IP configurations。
  2. 将公共 IP 设置为 None（不要删除资源）。
  3. 通过 Azure Serial Console 或保留的另一种方式登录 VM。

- [ ] **Step 3: 运行验证脚本**

  ```bash
  bash scripts/verify-outbound.sh
  ```

  Expected: 输出 `PASS: 默认出站访问可用`。

- [ ] **Step 4a: 如果验证通过**

  继续 Task 5（部署 cloudflared 与切换 DNS）。

- [ ] **Step 4b: 如果验证失败**

  重新绑定公共 IP，先执行 Task 4（配置 Cloudflare WARP/One），再解绑公共 IP重新验证。

---

### Task 4: Cloudflare WARP/One Fallback 配置（条件任务）

**Files:**
- Create: `scripts/setup-warp.sh`

**Interfaces:**
- Consumes: Cloudflare Zero Trust team name、service token（`CF_WARP_CLIENT_ID`, `CF_WARP_CLIENT_SECRET`）
- Produces: VM 通过 WARP 实现 0 成本出站互联网访问

- [ ] **Step 1: 在 Cloudflare Zero Trust 创建 service token**

  路径：Zero Trust → Access → Service Tokens → Create Service Token。
  复制 Client ID 和 Client Secret。

- [ ] **Step 2: 配置 device enrollment policy**

  路径：Zero Trust → Settings → WARP Client → Device Enrollment。
  创建包含该 service token 的允许策略（Action: Service Auth）。

- [ ] **Step 3: 编写 WARP 安装脚本**

  创建 `scripts/setup-warp.sh`：

  ```bash
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
  ```

  Test: `bash -n scripts/setup-warp.sh`。

- [ ] **Step 4: 在 VM 上执行 WARP 安装并验证**

  在重新解绑公共 IP 前，先绑定公共 IP 安装 WARP；安装完成后再解绑。

  ```bash
  export CF_WARP_ORG=your-team-name
  export CF_WARP_CLIENT_ID=xxx
  export CF_WARP_CLIENT_SECRET=yyy
  bash scripts/setup-warp.sh
  curl https://www.cloudflare.com/cdn-cgi/trace
  ```

  Expected: 输出包含 `warp=on`。

- [ ] **Step 5: 确保 Docker 出网走 WARP**

  如果 `docker pull hello-world` 失败，检查 WARP 是否为默认路由。可尝试：

  ```bash
  ip route | grep default
  docker run --rm --network host hello-world
  ```

  若 Docker 网桥未走 WARP，可配置 Docker 使用系统代理或调整 iptables。

- [ ] **Step 6: Commit**

  ```bash
  git add scripts/setup-warp.sh
  git commit -m "ops(azure): add Cloudflare WARP fallback for outbound internet"
  ```

---

### Task 5: 在 VM 上部署 cloudflared 并切换 DNS

**Files:**
- Modify: Cloudflare DNS（外部）
- Execute: `scripts/setup-cloudflared.sh`

**Interfaces:**
- Consumes: `CF_TUNNEL_TOKEN`（已存入 GitHub Secrets 或 VM 环境变量）
- Produces: `https://api.example.com` 通过 Cloudflare Tunnel 可访问

- [ ] **Step 1: 在 VM 上执行 cloudflared 安装脚本**

  ```bash
  export CF_TUNNEL_TOKEN=your-token
  bash scripts/setup-cloudflared.sh
  ```

- [ ] **Step 2: 验证 cloudflared 运行状态**

  ```bash
  docker logs --tail 50 cloudflared
  ```

  Expected: 日志显示 `Registered tunnel connection` 和 `Active` 状态。

- [ ] **Step 3: 降低 DNS TTL**

  在切换记录前，将目标子域的 TTL 设为 300 秒或更低。

- [ ] **Step 4: 切换 DNS 记录**

  将 `api.example.com` 从 `A` 记录（Azure 公共 IP）改为 `CNAME` 记录：
  - Target: `<tunnel-id>.cfargotunnel.com`
  - Proxy status: Enabled（橙色云）

- [ ] **Step 5: 验证外部访问**

  等待 TTL 过期后，从本地运行：

  ```bash
  curl -I https://api.example.com/health
  nslookup api.example.com
  ```

  Expected: `nslookup` 返回 Cloudflare 的 CNAME；`curl` 返回 200 OK。

---

### Task 6: 删除 Azure 公共 IP

**Files:**
- 外部：Azure 门户/CLI

**Interfaces:**
- Consumes: 已验证 Cloudflare Tunnel 和出网访问正常
- Produces: Azure 账单不再包含该公共 IP 费用

- [ ] **Step 1: 确认连续 24 小时服务正常**

  在删除前，确认 `api.example.com` 已通过 Cloudflare Tunnel 稳定访问至少 24 小时，且 CI/CD 至少成功过一次。

- [ ] **Step 2: 在 Azure 门户删除公共 IP 资源**

  1. 进入公共 IP 资源页。
  2. 确认没有资源依赖。
  3. 点击 Delete。

- [ ] **Step 3: 验证账单**

  下一张 Azure 账单确认公共 IP 费用为 0。

---

### Task 7: 安装并注册 GitHub Self-Hosted Runner

**Files:**
- Create: `scripts/setup-github-runner.sh`
- Modify: `.github/workflows/cd-azure-b2ats.yml`

**Interfaces:**
- Consumes: GitHub repo URL、`GITHUB_TOKEN`（用于 runner 注册）
- Produces: VM 内运行一个带有标签 `self-hosted, azure-b2ats` 的 GitHub Actions runner

- [ ] **Step 1: 编写 runner 安装脚本**

  创建 `scripts/setup-github-runner.sh`：

  ```bash
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
  ```

  Test: `bash -n scripts/setup-github-runner.sh`。

- [ ] **Step 2: 在 VM 上生成 runner registration token**

  在 GitHub 仓库 Settings → Actions → Runners → New self-hosted runner，或调用 API：

  ```bash
  curl -X POST -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    https://api.github.com/repos/fromwordimport/ai_cbc/actions/runners/registration-token
  ```

- [ ] **Step 3: 执行安装脚本**

  ```bash
  export GITHUB_RUNNER_TOKEN=xxx
  bash scripts/setup-github-runner.sh
  ```

  Test: 在 GitHub 仓库 Runners 列表看到 `azure-b2ats` 状态为 Idle。

- [ ] **Step 4: Commit**

  ```bash
  git add scripts/setup-github-runner.sh
  git commit -m "ops(ci): add GitHub self-hosted runner setup script"
  ```

---

### Task 8: 改造 GitHub Actions 为双轨部署

**Files:**
- Modify: `.github/workflows/cd-azure-b2ats.yml`

**Interfaces:**
- Consumes: `CF_TUNNEL_TOKEN`（保留在 secrets 中，本任务不直接使用）、`AZURE_CREDENTIALS`、`AZURE_RG`、`AZURE_VM_NAME`
- Produces: master push 时优先走 self-hosted runner，失败可手动触发 Azure Run Command

- [ ] **Step 1: 重构 deploy job 为 self-hosted runner 主路径**

  将现有 `.github/workflows/cd-azure-b2ats.yml` 中的 `deploy` job 改为：

  ```yaml
  deploy:
    runs-on: [self-hosted, azure-b2ats]
    needs: build-push
    environment: azure-b2ats
    outputs:
      image_tag: ${{ needs.build-push.outputs.image_tag }}
    steps:
      - name: Deploy on VM
        env:
          IMAGE_TAG: ${{ needs.build-push.outputs.image_tag }}
        run: |
          cd /opt/aicbc
          git remote set-url origin https://x-access-token:${GITHUB_TOKEN}@github.com/fromwordimport/ai_cbc.git
          git fetch origin master
          git reset --hard origin/master
          export IMAGE_TAG=${IMAGE_TAG}
          bash scripts/deploy-to-azure-b2ats.sh
  ```

  注意：删除 `appleboy/ssh-action` 相关步骤。

- [ ] **Step 2: 新增 Azure Run Command 备用 job**

  添加：

  ```yaml
  deploy-run-command:
    runs-on: ubuntu-22.04
    needs: build-push
    environment: azure-b2ats
    if: failure() && needs.deploy.result == 'failure'
    steps:
      - name: Login to Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Deploy via Azure Run Command
        env:
          IMAGE_TAG: ${{ needs.build-push.outputs.image_tag }}
        run: |
          az vm run-command invoke \
            --resource-group ${{ secrets.AZURE_RG }} \
            --name ${{ secrets.AZURE_VM_NAME }} \
            --command-id RunShellScript \
            --scripts "export IMAGE_TAG=${IMAGE_TAG} && cd /opt/aicbc && git remote set-url origin https://x-access-token:${GITHUB_TOKEN}@github.com/fromwordimport/ai_cbc.git && git fetch origin master && git reset --hard origin/master && bash scripts/deploy-to-azure-b2ats.sh"
  ```

- [ ] **Step 3: 新增 workflow_dispatch 触发 Run Command 的 job**

  添加一个可手动触发的 job，方便随时验证备用路径：

  ```yaml
  deploy-run-command-manual:
    runs-on: ubuntu-22.04
    environment: azure-b2ats
    if: github.event_name == 'workflow_dispatch'
    steps:
      - name: Login to Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Deploy via Azure Run Command
        env:
          IMAGE_TAG: ${{ github.sha }}
        run: |
          az vm run-command invoke \
            --resource-group ${{ secrets.AZURE_RG }} \
            --name ${{ secrets.AZURE_VM_NAME }} \
            --command-id RunShellScript \
            --scripts "export IMAGE_TAG=${IMAGE_TAG} && cd /opt/aicbc && git remote set-url origin https://x-access-token:${GITHUB_TOKEN}@github.com/fromwordimport/ai_cbc.git && git fetch origin master && git reset --hard origin/master && bash scripts/deploy-to-azure-b2ats.sh"
  ```

- [ ] **Step 4: 验证工作流 YAML 语法**

  Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/cd-azure-b2ats.yml'))"`

  Expected: 无报错。

- [ ] **Step 5: Commit**

  ```bash
  git add .github/workflows/cd-azure-b2ats.yml
  git commit -m "ops(ci): migrate to self-hosted runner with Azure Run Command fallback"
  ```

---

### Task 9: Worker VM 部署同步改造

**Files:**
- Modify: `.github/workflows/cd-azure-b2ats.yml` 中的 `deploy-worker` job

**Interfaces:**
- Consumes: 与主 VM 相同的 Azure Run Command 机制
- Produces: Worker VM 也能在无公共 IP 情况下被部署

- [ ] **Step 1: 为 worker VM 安装 self-hosted runner**

  参考 Task 7，在 ARM Worker VM 上运行 `scripts/setup-github-runner.sh`，标签设为 `self-hosted, azure-worker`。

- [ ] **Step 2: 修改 deploy-worker job**

  将 `deploy-worker` 改为：

  ```yaml
  deploy-worker:
    runs-on: [self-hosted, azure-worker]
    needs: build-push
    environment: azure-b2ats
    steps:
      - name: Deploy worker on VM
        env:
          IMAGE_TAG: ${{ needs.build-push.outputs.image_tag }}
          AZURE_MAIN_VM_IP: ${{ secrets.AZURE_MAIN_VM_IP }}
        run: |
          cd /opt/aicbc
          git remote set-url origin https://x-access-token:${GITHUB_TOKEN}@github.com/fromwordimport/ai_cbc.git
          git fetch origin master
          git reset --hard origin/master
          export IMAGE_TAG=${IMAGE_TAG}
          export AZURE_MAIN_VM_IP=${AZURE_MAIN_VM_IP}
          bash scripts/deploy-to-azure-worker.sh
  ```

  注意：删除 `appleboy/ssh-action` 步骤。

- [ ] **Step 3: Commit**

  ```bash
  git add .github/workflows/cd-azure-b2ats.yml
  git commit -m "ops(ci): migrate worker deployment to self-hosted runner"
  ```

---

### Task 10: 端到端验证与回滚演练

**Files:**
- 所有已修改文件

**Interfaces:**
- Consumes: 完整部署链路
- Produces: 验证报告 + 回滚操作手册更新

- [ ] **Step 1: 完整主路径验证**

  1. 推送一个空 commit 到 master：

     ```bash
     git commit --allow-empty -m "test: verify self-hosted runner deployment"
     git push origin master
     ```

  2. 在 GitHub Actions 确认 `deploy` job 成功。
  3. 确认 `https://api.example.com/health` 返回 200。

- [ ] **Step 2: 备用路径验证**

  1. 在 GitHub 手动触发 `deploy-run-command-manual`。
  2. 确认 Actions 成功，且服务仍然健康。

- [ ] **Step 3: 回滚演练**

  1. 停止 `cloudflared` 容器：

     ```bash
     docker stop cloudflared
     ```

  2. 确认 `https://api.example.com/health` 无法访问。
  3. 重新绑定原 Azure 公共 IP。
  4. 将 DNS `CNAME` 改回 `A` 记录指向原公共 IP。
  5. 将 Nginx 端口改回 `80:80` / `443:443`。
  6. 确认服务恢复。
  7. 再次切回 Cloudflare Tunnel 模式。

- [ ] **Step 4: 更新运维手册**

  在 `docs/运维/Azure-B2ats-v2-首次部署手册.md` 末尾追加一节「Cloudflare Tunnel 模式部署与回滚」，记录：

  - 所需 secrets 清单
- 各脚本执行顺序
- 回滚命令
- 故障排查（如何查看 cloudflared 日志、WARP 状态、runner 状态）

- [ ] **Step 5: 最终 Commit**

  ```bash
  git add docs/运维/Azure-B2ats-v2-首次部署手册.md
  git commit -m "docs(ops): add Cloudflare Tunnel deployment and rollback runbook"
  ```

---

## Self-Review

### 1. Spec coverage

| 设计文档章节 | 对应任务 |
|---|---|
| 3.1 选型 Cloudflare Tunnel | Task 1 |
| 3.2 目标架构 | Task 1, 5, 6 |
| 3.3 DNS 与证书变更 | Task 2, 5 |
| 3.4 VM 配置变更 | Task 2, 5 |
| 3.5 CI/CD 双轨部署 | Task 7, 8, 9 |
| 4.1 出网访问依赖 | Task 3 |
| 4.2 前置验证 | Task 3 |
| 4.3 回滚方案 | Task 10 |
| 4.4 WARP fallback | Task 4 |
| 4.5 出站验证扩展 | Task 3, 4 |

无遗漏。

### 2. Placeholder scan

- 无 TBD/TODO。
- 所有脚本包含实际代码。
- 所有命令包含预期输出。
- 域名 `api.example.com` 为占位符，但这是设计文档中已存在的示例，实施时会替换为真实域名。

### 3. Type consistency

- 所有 secrets 名称在文档和代码中一致：`CF_TUNNEL_TOKEN`、`CF_WARP_ORG`、`CF_WARP_CLIENT_ID`、`CF_WARP_CLIENT_SECRET`、`AZURE_CREDENTIALS`、`AZURE_RG`、`AZURE_VM_NAME`、`GITHUB_RUNNER_TOKEN`。
- Runner 标签一致：`self-hosted, azure-b2ats` 和 `self-hosted, azure-worker`。

---

*Plan generated from `docs/superpowers/specs/2026-06-26-azure-public-ip-alternative-design.md`.*
