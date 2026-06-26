# Cloudflare Tunnel 部署与 DNS 切换手册

> **版本**：v1.0  
> **日期**：2026-06-26  
> **状态**：待实施  
> **负责人**：小维（DevOps/MLOps）  
> **前置条件**：已完成 [Cloudflare Tunnel 人工配置手册](MANUAL-cloudflare-setup.md)（Task 1），已获取 `CF_TUNNEL_TOKEN` 和 Tunnel ID。

## 概述

本文档指导人工操作员在 Azure VM 上部署 cloudflared 容器，并将生产流量从 Azure 公共 IP 切换到 Cloudflare Tunnel。所有涉及真实 VM 和 Cloudflare 仪表盘的步骤必须由持有相应权限的人员手动执行。

---

## 步骤 1：在 VM 上执行 cloudflared 安装脚本

1. 通过 SSH 登录到 Azure B2ats v2 VM：
   ```bash
   ssh user@<vm-public-ip>
   ```

2. 进入项目目录：
   ```bash
   cd ~/ai_cbc
   ```

3. 设置环境变量并执行脚本：
   ```bash
   export CF_TUNNEL_TOKEN="your-tunnel-token-here"
   bash scripts/setup-cloudflared.sh
   ```
   - `CF_TUNNEL_TOKEN` 为 Cloudflare Tunnel 创建时生成的 JWT 字符串（以 `eyJ` 开头）。
   - 若 token 已写入 VM 的 `/etc/environment` 或 systemd 环境变量，可直接执行脚本。

4. 脚本执行完成后，预期输出：
   ```
   cloudflared 隧道连接已注册
   ```

**验证标准**：脚本以退出码 0 结束，且输出包含 `cloudflared 隧道连接已注册`。

---

## 步骤 2：验证 cloudflared 运行状态

1. 查看 cloudflared 容器日志：
   ```bash
   docker logs --tail 50 cloudflared
   ```

2. 预期日志内容包含以下关键字：
   - `Registered tunnel connection` — 表示隧道已成功注册到 Cloudflare。
   - `Active` 或 `connIndex=0` 连接状态 — 表示隧道处于活跃状态。

3. 使用辅助脚本快速检查：
   ```bash
   bash scripts/check-tunnel.sh
   ```
   - 退出码 0：容器运行且日志正常。
   - 退出码 1：容器未运行或日志异常，需排查。

**验证标准**：日志显示 `Registered tunnel connection` 和 `Active` 状态；`check-tunnel.sh` 返回退出码 0。

---

## 步骤 3：降低 DNS TTL

在切换 DNS 记录前，先将目标子域名的 TTL 调低，以缩短全球 DNS 缓存刷新时间，避免切换后长时间无法生效。

1. 打开浏览器，访问 [Cloudflare 仪表盘](https://dash.cloudflare.com)。
2. 选择目标域名（如 `example.com`），进入 **DNS** → **记录**。
3. 找到现有的 `A` 记录：
   - 名称：`api`（或你的子域名前缀）
   - 内容：当前 Azure VM 的公共 IP 地址
4. 点击该记录右侧的 **编辑** 按钮。
5. 将 **TTL** 字段修改为 **300 秒**（或更低，如 1 分钟/Auto）。
6. 点击 **保存**。

> **注意**：若原 TTL 为 1 小时（3600 秒），则需等待最多 1 小时让旧 TTL 在全球 DNS 缓存中过期。建议在非高峰时段提前执行此步骤。

**验证标准**：DNS 记录页面显示该 `A` 记录的 TTL 为 300 秒或更低。

---

## 步骤 4：切换 DNS 记录

待旧 TTL 过期后（或确认缓存已刷新），将 DNS 记录从 A 记录切换为 CNAME 记录。

1. 在 Cloudflare DNS 记录页面，找到目标子域名（如 `api`）的 `A` 记录。
2. 点击该记录右侧的 **编辑** 按钮。
3. 修改记录类型和参数：
   - **类型**：将 `A` 改为 `CNAME`
   - **目标**：`<tunnel-id>.cfargotunnel.com`
     - 例如：`12345678-1234-1234-1234-123456789abc.cfargotunnel.com`
   - **代理状态**：**已启用**（橙色云图标）
   - **TTL**：保持 300 秒或 Auto
4. 点击 **保存**。

> **注意**：CNAME 目标中的 `<tunnel-id>` 为 Cloudflare Tunnel 创建时分配的 UUID，可在 Zero Trust → Networks → Tunnels → 隧道详情页的 **Overview** 标签页找到。

**验证标准**：DNS 记录列表中显示 `api.example.com` 为 `CNAME` 类型，目标为 `<tunnel-id>.cfargotunnel.com`，代理状态为橙色云。

---

## 步骤 5：验证外部访问

等待 DNS 传播完成后（通常几分钟内，取决于 TTL），从本地机器验证外部访问。

1. 检查 DNS 解析：
   ```bash
   nslookup api.example.com
   ```
   - 预期返回：CNAME 链指向 `<tunnel-id>.cfargotunnel.com`，最终解析到 Cloudflare 边缘节点 IP（如 `104.16.x.x` 或 `172.64.x.x`）。

2. 检查 HTTP 连通性：
   ```bash
   curl -I https://api.example.com/health
   ```
   - 预期返回：HTTP/2 200 OK，响应头包含 `cloudflare` 或 `cf-ray` 等 Cloudflare 标识。

3. 检查端到端业务接口：
   ```bash
   curl https://api.example.com/health
   ```
   - 预期返回 JSON：`{"status":"ok"}` 或类似健康检查响应。

**验证标准**：`nslookup` 返回 Cloudflare CNAME 链；`curl -I` 返回 200 OK；业务接口响应正常。

---

## 回滚步骤

若切换后出现问题，可按以下步骤回滚到 Azure 公共 IP 方案：

1. **停止 cloudflared 容器**：
   ```bash
   docker stop cloudflared && docker rm cloudflared
   ```

2. **切换 DNS 记录回 A 记录**：
   - 在 Cloudflare DNS 记录页面，将 `api.example.com` 的 `CNAME` 记录改回 `A` 记录。
   - **内容**：填写原 Azure VM 的公共 IP 地址（切换前记录的值）。
   - **代理状态**：保持橙色云（已启用）。
   - **TTL**：可恢复为原值（如 1 小时）。

3. **重新绑定公共 IP（如已解绑）**：
   - 若已在 Azure 门户中解绑公共 IP，需重新绑定到 VM 的网络接口。
   - 在 Azure 门户 → 虚拟机 → 网络 → 网络接口 → IP 配置 → 关联公共 IP。

4. **验证回滚**：
   ```bash
   nslookup api.example.com
   curl -I https://api.example.com/health
   ```
   - 预期 `nslookup` 返回 Azure 公共 IP；`curl` 返回 200 OK。

> **注意**：回滚后 cloudflared 容器已停止，Tunnel 状态在 Cloudflare 控制台会显示为 **Down**，这是正常的，不影响公共 IP 访问。

---

> **占位符说明**：本文档中的 `api.example.com` 和 `<tunnel-id>` 仅为占位符，实际操作时请替换为你的真实子域名和 Tunnel UUID。
