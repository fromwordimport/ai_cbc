# Cloudflare Tunnel 人工配置手册

> **版本**：v1.0  
> **日期**：2026-06-26  
> **状态**：待实施  
> **负责人**：小维（DevOps/MLOps）

## 概述

本文档指导人工操作员在 Cloudflare 仪表盘中完成 Tunnel 创建和 Public Hostname 配置。这些步骤涉及 Cloudflare 账户权限，必须由持有账户凭证的人员手动执行，无法自动化。

## 前置条件

- 拥有目标域名的 Cloudflare 账户管理员权限
- 已确认 Azure VM 的公共 IP 地址（用于核对现有 DNS 记录）
- 已准备好 GitHub 仓库的管理员权限（用于添加 Secrets）

---

## 步骤 1：确认 Cloudflare DNS 权限

1. 打开浏览器，访问 [Cloudflare 仪表盘](https://dash.cloudflare.com)。
2. 使用管理员账户登录。
3. 在首页域名列表中，确认目标域名（如 `example.com`）已托管在 Cloudflare。
   - 若域名不在列表中，说明 DNS 未托管在 Cloudflare，需先将域名 DNS 服务器切换为 Cloudflare 提供的名称服务器。
4. 点击目标域名，进入该域名的管理页面。
5. 在左侧导航栏选择 **DNS** → **记录**。
6. 在 DNS 记录列表中，查找现有的 `A` 记录：
   - 名称：`api`（或你的子域名前缀）
   - 内容：当前 Azure VM 的公共 IP 地址
   - 代理状态：橙色云（已启用 Cloudflare 代理）或灰色云（仅 DNS）
7. 记录该 `A` 记录的当前内容（Azure 公共 IP），以便回滚时使用。

**验证标准**：在 Cloudflare DNS 记录页面能看到目标域名，且存在指向 Azure 公共 IP 的 `A` 记录。

---

## 步骤 2：创建 Cloudflare Tunnel

1. 在 Cloudflare 仪表盘左侧导航栏，选择 **Zero Trust**。
   - 若首次进入 Zero Trust，可能需要选择组织名称（Team name），按提示完成初始化。
2. 在 Zero Trust 控制台左侧导航栏，选择 **Networks** → **Tunnels**。
3. 点击页面右上角的 **Create a tunnel** 按钮。
4. 在弹出的选择连接器类型页面中，选择 **Cloudflared**（默认选项）。
5. 点击 **Next**。
6. 在 **Name your tunnel** 页面，输入隧道名称：
   - **Tunnel Name**: `aicbc-azure-b2ats`
7. 点击 **Save tunnel**。
8. 在 **Choose your environment** 页面，选择 **Docker**（或 Debian，根据偏好）。
9. 页面会显示一个 **Tunnel token**，格式为一长串 JWT 字符串（以 `eyJ` 开头）。
10. 点击 token 右侧的复制按钮，将完整 token 复制到剪贴板。
11. 立即将 token 保存到密码管理器或安全位置——**该 token 只在此页面显示一次**，离开页面后无法再次查看完整 token。

**验证标准**：在 Cloudflare Zero Trust → Networks → Tunnels 列表中能看到名为 `aicbc-azure-b2ats` 的隧道，状态为 **Healthy**（待 cloudflared 运行后）或 **Down**（尚未连接）。

---

## 步骤 3：保存 Tunnel Token 到 GitHub Secrets

1. 打开浏览器，访问 GitHub 仓库页面：`https://github.com/fromwordimport/ai_cbc`。
2. 点击顶部导航栏的 **Settings**。
3. 在左侧导航栏选择 **Secrets and variables** → **Actions**。
4. 点击 **New repository secret** 按钮。
5. 在 **Name** 字段输入：`CF_TUNNEL_TOKEN`
6. 在 **Secret** 字段粘贴步骤 2 中复制的 tunnel token。
7. 点击 **Add secret**。

**验证标准**：在 GitHub 仓库 Settings → Secrets and variables → Actions 页面能看到 `CF_TUNNEL_TOKEN` 条目。

---

## 步骤 4：配置 Public Hostname

1. 返回 Cloudflare Zero Trust 控制台，进入 **Networks** → **Tunnels**。
2. 在隧道列表中点击 `aicbc-azure-b2ats`。
3. 在隧道详情页面，选择 **Public Hostnames** 标签页。
4. 点击 **Add a public hostname** 按钮。
5. 填写以下字段：
   - **Subdomain**: `api`
   - **Domain**: 选择你的目标域名（如 `example.com`）
   - **Path**: 留空
   - **Type**: `HTTP`
   - **URL**: `http://localhost:80`
6. 点击 **Save hostname**。

**验证标准**：在 Public Hostnames 列表中能看到新添加的记录，显示为 `api.example.com` → `http://localhost:80`。

---

## 步骤 5：记录 CNAME 目标

1. 在隧道详情页面的 **Overview** 标签页，找到 **Tunnel ID**。
   - 格式类似 `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`。
2. 完整的 CNAME 目标为：
   - `<TUNNEL_ID>.cfargotunnel.com`
   - 例如：`12345678-1234-1234-1234-123456789abc.cfargotunnel.com`
3. 记录该 CNAME 目标，后续 DNS 切换步骤需要用到。

---

## 后续步骤

完成上述人工配置后，继续执行以下自动化步骤：

1. 在 Azure VM 上运行 `scripts/setup-cloudflared.sh` 启动 cloudflared 容器。
2. 在 Cloudflare DNS 中将原有的 `A` 记录（指向 Azure 公共 IP）改为 `CNAME` 记录，指向 `<TUNNEL_ID>.cfargotunnel.com`。
3. 验证 `api.example.com` 可通过 Cloudflare Tunnel 正常访问。
4. 确认无误后，在 Azure 门户中解绑并删除 VM 的公共 IP。

## 回滚信息

若需要回滚到公共 IP 方案：
1. 在 Azure 门户重新绑定原有的公共 IP。
2. 在 Cloudflare DNS 中将 `CNAME` 记录改回 `A` 记录，指向原 Azure 公共 IP。
3. 停止并删除 cloudflared 容器：`docker stop cloudflared && docker rm cloudflared`。

---

> **注意**：本手册中的 `example.com` 仅为占位符，实际操作时请替换为你的真实域名。
