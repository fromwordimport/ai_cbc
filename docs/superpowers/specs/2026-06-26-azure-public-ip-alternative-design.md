# Azure 公共 IP 免费替代方案设计

> **版本**：v1.0  
> **日期**：2026-06-26  
> **状态**：待实施  
> **负责人**：小维（DevOps/MLOps）

## 1. 背景与目标

当前 AI_CBC 生产环境使用 Azure B2ats v2 虚拟机，并通过一个**付费的 Azure 公共 IP**暴露入口。该公共 IP 用于：

- 用户通过 HTTPS 访问 AI_CBC API 与前端。
- GitHub Actions 通过 SSH 登录 VM 执行自动部署。

**目标**：在核心功能不变的前提下，使用**完全免费**的服务替代该付费公共 IP。若当前平台政策下无法实现 0 成本稳定运行，则宁可维持现状，也不引入任何付费组件。

## 2. 当前架构

- **主 VM**：Azure B2ats v2（1 GiB RAM），运行 API、MongoDB、Redis、Nginx。
- **Worker VM**：ARM64 VM，运行 Celery worker。
- **入口**：Nginx 监听 `80/443`，绑定 Azure 公共 IP。
- **DNS**：Cloudflare 子域名通过 `A` 记录指向该公共 IP。
- **证书**：Let's Encrypt（Certbot）自动续期。
- **CI/CD**：`.github/workflows/cd-azure-b2ats.yml` 通过 `appleboy/ssh-action` 直连 `secrets.AZURE_VM_IP`。

## 3. 设计方案

### 3.1 选型

采用 **Cloudflare Tunnel** 作为 Azure 公共 IP 的免费替代方案，配合 **Cloudflare 边缘 HTTPS** 与 **Cloudflare Origin CA** 证书。

选择理由：

- DNS 已经在 Cloudflare，迁移只需把 `A` 记录改为 `CNAME`。
- Cloudflare Tunnel 免费版足以承载当前流量。
- 可同时获得 CDN、DDoS 防护、边缘 HTTPS、源站 IP 隐藏。
- 与现有 Nginx + Docker Compose 架构兼容，改动最小。

### 3.2 目标架构

```text
                         ┌─────────────────────┐
  用户 / GitHub Actions  │   Cloudflare 边缘    │
───────────────────────► │  (CDN / DDoS / TLS)  │
                         └──────────┬──────────┘
                                    │
                         cloudflared tunnel
                         (VM 内守护进程)
                                    │
                         ┌──────────▼──────────┐
                         │   Azure B2ats v2    │
                         │   VM（仅私有 IP）    │
                         │  ┌───────────────┐  │
                         │  │    Nginx      │  │
                         │  │   80 / 443    │  │
                         │  └───────┬───────┘  │
                         │          │          │
                         │  ┌───────▼───────┐  │
                         │  │  FastAPI API  │  │
                         │  └───────────────┘  │
                         └─────────────────────┘
```

### 3.3 DNS 与证书变更

| 组件 | 当前 | 变更后 |
|---|---|---|
| DNS 记录 | `A` 记录指向 Azure 公共 IP | `CNAME` 指向 `<tunnel-id>.cfargotunnel.com` |
| VM 公共 IP | 绑定并收费 | 解绑并删除 |
| HTTPS 证书 | Let's Encrypt（Certbot） | Cloudflare 边缘自动 HTTPS + Cloudflare Origin CA |

弃用 Certbot 后，Nginx 使用 Cloudflare Origin CA 15 年期证书，无需自动续期逻辑。

### 3.4 VM 配置变更

1. 在 Azure 门户/CLI 中解绑并删除 VM 网络接口上的公共 IP。
2. 安装并运行 `cloudflared`：

   ```bash
   docker run -d --name cloudflared \
     --restart unless-stopped \
     cloudflare/cloudflared:latest tunnel --no-autoupdate run --token $TUNNEL_TOKEN
   ```

3. 调整 NSG/防火墙：
   - 入站：关闭外部 `80/443/22`，仅允许来自 `cloudflared` 本地回环的流量。
   - 出站：允许 HTTPS（443）、DNS（53）到 Cloudflare 边缘与 GitHub API。
4. 安全加固 Nginx 绑定：将 `docker-compose.azure-b2ats.yml` 中 Nginx 端口映射从 `80:80` / `443:443` 改为 `127.0.0.1:80:80` / `127.0.0.1:443:443`，确保 Nginx 不监听 VM 外部接口，只有本地 `cloudflared` 能访问。

### 3.5 CI/CD 双轨部署

保留 GitHub Actions 自动部署能力，建立主备两条 0 成本路径：

#### 主路径：Self-Hosted Runner

在 VM 内注册 GitHub Actions self-hosted runner，标签为 `self-hosted, azure-b2ats`。

```yaml
deploy-self-hosted:
  runs-on: [self-hosted, azure-b2ats]
  needs: build-push
  steps:
    - name: Deploy on VM
      run: |
        cd /opt/aicbc
        git fetch origin master
        git reset --hard origin/master
        export IMAGE_TAG=${{ github.sha }}
        bash scripts/deploy-to-azure-b2ats.sh
```

runner 通过 Azure 默认出站访问连接 GitHub API。这是 0 成本方案成立的关键依赖之一。

#### 备用路径：Azure Run Command

当 self-hosted runner 不可用时，使用 Azure Run Command 直接在 VM 上执行部署脚本。该方式通过 Azure 管理平面访问 VM，**不需要公共 IP，也不需要 SSH**。

```yaml
deploy-azure-run-command:
  runs-on: ubuntu-22.04
  needs: build-push
  steps:
    - name: Login to Azure
      uses: azure/login@v2
      with:
        creds: ${{ secrets.AZURE_CREDENTIALS }}
    - name: Run deploy script on VM
      run: |
        az vm run-command invoke \
          --resource-group ${{ secrets.AZURE_RG }} \
          --name ${{ secrets.AZURE_VM_NAME }} \
          --command-id RunShellScript \
          --scripts "cd /opt/aicbc && git fetch origin master && git reset --hard origin/master && export IMAGE_TAG=${{ github.sha }} && bash scripts/deploy-to-azure-b2ats.sh"
```

Azure Run Command 仅产生标准 VM 计算费用（B2ats v2 本身在免费额度内），不产生额外的公共 IP 或 Bastion 费用。

## 4. 0 成本关键前提

### 4.1 出网访问依赖

去掉公共 IP 后，VM 需要稳定的互联网出网能力才能：

- `docker pull` 拉取镜像
- `apt-get update` / `git fetch`
- `cloudflared` 连接 Cloudflare 边缘

Azure 对没有公共 IP 的 VM 提供「默认出站访问」（Default Outbound Access），这是 0 成本的 SNAT 出网方式。但微软正在逐步弃用该功能，不同订阅和区域的可用性可能不同。

**本方案成立的唯一前提：当前订阅/区域仍可使用 Azure 默认出站访问。**

### 4.2 前置验证步骤

在实施任何变更前，必须完成以下可回滚验证：

1. 在 Azure 门户中将 VM 公共 IP 临时「解绑」（不要删除）。
2. 通过 Azure Serial Console 或其他非公共 IP 方式登录 VM。
3. 执行以下测试：

   ```bash
   curl -I https://cloudflare.com
   docker pull ghcr.io/fromwordimport/ai_cbc:latest
   git fetch origin master
   ```

4. 如果全部通过，说明 0 成本前提成立，可以继续实施。
5. 如果有任何一项失败，说明在当前 Azure 政策下无法以 0 成本替代公共 IP，应**立即停止并回滚**（重新绑定公共 IP）。

### 4.3 回滚方案

- 保留原 Azure 公共 IP 资源在实施完成前不删除，仅做解绑。
- 提前将原 DNS `A` 记录的 TTL 调低（例如 300 秒）。
- 若 Cloudflare Tunnel 或出网访问异常，立即：
  1. 重新绑定原公共 IP。
  2. 将 DNS `CNAME` 改回 `A` 记录。
  3. 恢复原有 Nginx + Certbot 配置。

### 4.4 默认出站访问不可用时的免费 fallback 方案

如果 Azure 默认出站访问已被禁用，Cloudflare Tunnel 本身也无法建立连接（`cloudflared` 需要访问 `*.argotunnel.com` 和 Cloudflare 边缘）。此时需要额外的免费出站方案。以下是按推荐度排序的备选：

#### 方案 F1：Cloudflare WARP / Cloudflare One（推荐）

在 VM 上安装 **Cloudflare One Client（WARP）**，将 VM 作为 headless 设备加入 Cloudflare Zero Trust 团队。Zero Trust 免费计划支持最多 50 个用户/设备，无带宽限制，无需 Azure 公共 IP 即可让 VM 出站。

实施要点：

1. 在 Cloudflare Zero Trust 控制台创建 service token。
2. 配置 device enrollment 策略，允许该 service token。
3. 在 VM 上安装 WARP 客户端：

   ```bash
   curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | \
     sudo gpg --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] \
     https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | \
     sudo tee /etc/apt/sources.list.d/cloudflare-client.list
   sudo apt update && sudo apt install cloudflare-warp
   ```

4. 创建 MDM 配置文件 `/var/lib/cloudflare-warp/mdm.xml`：

   ```xml
   <dict>
     <key>auth_client_id</key>
     <string>YOUR_CLIENT_ID</string>
     <key>auth_client_secret</key>
     <string>YOUR_CLIENT_SECRET</string>
     <key>organization</key>
     <string>your-team-name</string>
     <key>auto_connect</key>
     <integer>1</integer>
     <key>service_mode</key>
     <string>warp</string>
     <key>onboarding</key>
     <false/>
   </dict>
   ```

5. 启用并启动服务：

   ```bash
   sudo systemctl enable --now warp-svc
   warp-cli connect
   ```

6. 验证：

   ```bash
   curl https://www.cloudflare.com/cdn-cgi/trace
   # 期望看到 warp=on
   ```

7. 确保 Docker 流量也走 WARP。如果默认路由未覆盖 Docker 网桥，可配置 Docker daemon 使用系统代理，或让 WARP 作为默认网关。

注意事项：

- 必须使用 **Cloudflare Zero Trust** 免费计划，而不是 consumer WARP。服务器通过 consumer WARP 出站可能违反服务条款。
- WARP 是 0 成本方案，但会引入少量额外延迟。

#### 方案 F2：Cloudflare WARP Connector

如果未来需要把整个 Azure 子网都接入 Cloudflare，可使用 **WARP Connector**（2026 年已 GA）。它本质上是 site-to-site VPN，允许子网内所有设备通过 Cloudflare 网络出站，也包含在 Zero Trust 免费计划中。当前单 VM 场景下，F1 更简单。

#### 方案 F3：第三方免费云 + WireGuard/Tailscale 网关

如果已有或愿意注册其他云平台的免费套餐（如 **Oracle Cloud Free Tier** 提供 2 个免费 AMD VM + 免费公共 IP），可在该平台创建一台 tiny gateway，然后：

- 在 Azure VM 和 gateway 之间建立 **WireGuard** 或 **Tailscale** 隧道。
- 将 gateway 配置为 exit node / NAT 出口。
- Azure VM 的默认路由指向该隧道，从而通过 gateway 免费出网。

该方案 0 成本，但需要维护第二朵云的基础设施，复杂度高于 F1。

#### 方案 F4：通过 Azure Run Command 推送部署包（有限适用）

如果 VM 完全不能出网，可让 GitHub Actions 在构建阶段把 Docker 镜像导出为 tar，再尝试通过 Azure Run Command 传入 VM 并导入。但 Azure Run Command 对输入脚本大小有限制，大镜像分片传递不可靠，**仅作为极端情况下的临时手段**，不推荐作为常规方案。

### 4.5 出站验证扩展

若 4.2 验证失败（默认出站访问不可用），则继续验证 F1：

1. 重新绑定公共 IP，安装并配置 Cloudflare WARP（F1）。
2. 解绑公共 IP。
3. 执行以下测试：

   ```bash
   curl -I https://cloudflare.com
   docker pull ghcr.io/fromwordimport/ai_cbc:latest
   git fetch origin master
   cloudflared tunnel --no-autoupdate run --token $TUNNEL_TOKEN
   ```

4. 如果 WARP 能提供稳定出站且 Tunnel 正常建立，则 F1 成立，可继续实施。
5. 如果 F1 也不可行，则进入 F3（第三方免费云网关）评估，或接受无法在当前约束下实现 0 成本的事实。

## 5. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| Azure 默认出站访问不可用 | VM 无法拉镜像/同步代码，方案不可行 | 前置验证；启用 Cloudflare WARP/One 或第三方免费网关；仍失败则维持现状 |
| Cloudflare Tunnel 连接中断 | 外部无法访问服务 | 双轨 CI/CD 仍可在 VM 内工作；快速切回公共 IP |
| Azure Run Command 权限配置复杂 | 备用部署路径失败 | 以 self-hosted runner 为主，Run Command 仅作冗余；提前配置服务主体 |
| 域名/证书切换窗口服务闪断 | 用户短暂无法访问 | 低 TTL + 非高峰时段执行 |

## 6. 成功标准

- [ ] Azure VM 不再绑定任何公共 IP。
- [ ] `api.example.com` 通过 Cloudflare Tunnel 正常访问，HTTPS 有效。
- [ ] GitHub Actions 推送 master 后，self-hosted runner 能成功部署。
- [ ] 备用路径「Azure Run Command」也能成功部署。
- [ ] 每月 Azure 账单中不再产生公共 IP 费用。

## 7. 后续步骤

设计确认后，通过 `superpowers:writing-plans` 制定详细实施计划，包含：

1. Cloudflare Tunnel 创建与 token 配置。
2. VM 出网验证与公共 IP 解绑。
3. DNS 与证书切换。
4. Self-hosted runner 安装与注册。
5. Azure Run Command 备用部署路径配置。
6. CI/CD 工作流改造。
7. 验证与回滚演练。

## 8. 参考文档

- [Cloudflare Tunnel 官方文档](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [Cloudflare Origin CA certificates](https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/)
- [Azure 默认出站访问](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/default-outbound-access)
- [Azure Run Command 文档](https://learn.microsoft.com/en-us/azure/virtual-machines/run-command-overview)
- [Deploy the Cloudflare One Client on headless Linux machines](https://developers.cloudflare.com/cloudflare-one/tutorials/deploy-client-headless-linux/)
- [Cloudflare WARP Linux client docs](https://developers.cloudflare.com/warp-client/get-started/linux/)
