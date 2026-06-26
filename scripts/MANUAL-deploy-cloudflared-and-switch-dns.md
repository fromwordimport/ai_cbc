# 在 Azure VM 上部署 cloudflared 并切换 DNS 至 Cloudflare Tunnel

> **任务**：将生产环境入口从 Azure 公共 IP 迁移到 Task 1 创建的 Cloudflare Tunnel。  
> **执行方式**：以下步骤需在真实的 Azure VM 和 Cloudflare Dashboard 上由人工执行。  
> **适用分支**：`feature/azure-public-ip-alternative`

---

## 前置条件

- Azure VM 已安装 Docker（`setup-azure-vm.sh` 已完成）。
- Cloudflare Tunnel 已在 Task 1 中创建，且 `CF_TUNNEL_TOKEN` 已保存到 GitHub Secrets 或已安全传输到 VM。
- 拥有 Cloudflare Dashboard 的 DNS 编辑权限。
- 当前 DNS 记录：`api.example.com` → A 记录（Azure 公共 IP）。

---

## Step 1：在 VM 上执行 cloudflared 安装脚本

SSH 登录到 Azure VM，然后执行：

```bash
export CF_TUNNEL_TOKEN="your-token-here"
bash scripts/setup-cloudflared.sh
```

**说明**：
- `setup-cloudflared.sh` 会拉取 `cloudflare/cloudflared:latest` 镜像并以 host 网络模式运行容器。
- 脚本内置 30 秒健康检查，若日志中出现 `Registered tunnel connection` 或 `Active` 则自动退出并返回 0。
- 若失败，脚本会打印最近 30 行日志供排查。

---

## Step 2：验证 cloudflared 运行状态

使用本任务提供的辅助脚本：

```bash
bash scripts/check-tunnel.sh
```

**期望输出**：

```
=== cloudflared 容器状态: 运行中 ===

=== 最近 30 行日志 ===
... Registered tunnel connection ...
... Active ...
```

**手动验证**（如脚本不可用）：

```bash
docker ps -f name=cloudflared
docker logs --tail 50 cloudflared
```

---

## Step 3：降低 DNS TTL

在 Cloudflare Dashboard 中：

1. 进入目标域名的 **DNS** → **记录**。
2. 找到 `api.example.com` 的 A 记录。
3. 将 **TTL** 从默认值（如 Auto / 1 小时）改为 **300 秒**（5 分钟）或更低。
4. 保存。

> **目的**：缩短 TTL 可让后续 DNS 切换更快生效，减少回滚时的故障时间。

---

## Step 4：切换 DNS 记录

在同一 Cloudflare Dashboard 页面，**优先使用编辑方式**，避免删除 A 记录导致服务中断：

### 推荐方式：直接编辑 A 记录为 CNAME

1. 找到现有的 `api.example.com` A 记录（指向 Azure 公共 IP）。
2. **编辑**该记录：
   - **类型**：改为 `CNAME`
   - **目标**：`<tunnel-id>.cfargotunnel.com`（将 `<tunnel-id>` 替换为 Task 1 中创建的 Tunnel ID）
   - **代理状态**：**已代理**（橙色云图标，即 Proxy status = Enabled）
   - **TTL**：Auto（或保持 300 秒）
3. 保存。

> **警告**：在确认隧道状态为 `Active` 之前，**不要删除 A 记录**。删除后若隧道未就绪，将立即失去入口，导致服务完全不可访问。

### 备选方式：删除后新建（仅当 DNS 提供商不支持 A 改 CNAME 时）

若你的 DNS 提供商或 Cloudflare Dashboard 不支持将 A 记录直接编辑为 CNAME，请按以下顺序操作：

1. **先确认隧道状态**：执行 `bash scripts/check-tunnel.sh`，确认日志中包含 `Registered tunnel connection` 和 `Active`。
2. **删除**现有的 `api.example.com` A 记录（指向 Azure 公共 IP）。
3. **新建**一条 `api.example.com` 记录：
   - **类型**：`CNAME`
   - **目标**：`<tunnel-id>.cfargotunnel.com`
   - **代理状态**：**已代理**（橙色云图标）
   - **TTL**：Auto（或保持 300 秒）
4. 保存。

---

## Step 5：验证外部访问

等待 TTL 过期（最多 5 分钟），然后在本地终端执行：

```bash
# 验证 DNS 已指向 Cloudflare Tunnel
curl -I https://api.example.com/health

# 验证 DNS 解析结果
nslookup api.example.com
```

**期望结果**：

- `curl -I https://api.example.com/health` 返回 `HTTP/1.1 200 OK`（或 `HTTP/2 200`）。
- `nslookup api.example.com` 返回的 `canonical name` 为 `<tunnel-id>.cfargotunnel.com`，且解析 IP 为 Cloudflare 边缘节点 IP（非 Azure 公共 IP）。

---

## 回滚步骤

若切换后出现问题，按以下顺序回滚：

### 1. 停止 cloudflared

```bash
docker stop cloudflared
docker rm cloudflared
```

### 2. 恢复 DNS 为 A 记录

在 Cloudflare Dashboard：

1. 删除 `api.example.com` 的 CNAME 记录。
2. 重新添加 A 记录：
   - **类型**：`A`
   - **IPv4 地址**：Azure 公共 IP（原 IP）
   - **代理状态**：按需（若之前为橙色云，保持已代理）
   - **TTL**：300 秒或更低
3. 保存。

### 3. 重新绑定公共 IP（如已解绑）

若 Azure VM 的公共 IP 已被解绑或释放：

1. 登录 Azure Portal → 虚拟机 → 网络设置。
2. 将公共 IP 重新关联到 VM 的网络接口。
3. 确认防火墙规则（如 NSG、ufw）仍允许 443 入站。

### 4. 验证回滚

```bash
curl -I https://api.example.com/health
nslookup api.example.com
```

确认 `nslookup` 返回 Azure 公共 IP，且 `curl` 返回 200 OK。

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `scripts/setup-cloudflared.sh` | cloudflared 容器部署脚本（Task 1 产出） |
| `scripts/check-tunnel.sh` | 隧道健康检查辅助脚本（本任务产出） |
| 本文档 | 人工操作手册（本任务产出） |

---

> **注意**：本指南仅涉及 DNS 和隧道切换操作，不涉及应用代码或 Kubernetes 配置的变更。所有操作完成后，请在 `feature/azure-public-ip-alternative` 分支上记录执行结果。
