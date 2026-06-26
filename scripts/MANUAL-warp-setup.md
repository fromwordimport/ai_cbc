# Cloudflare WARP/One 人工配置手册

> **版本**：v1.0  
> **日期**：2026-06-26  
> **状态**：待实施  
> **负责人**：小维（DevOps/MLOps）

## 概述

本文档指导人工操作员在 Cloudflare Zero Trust 中创建 service token、配置 device enrollment policy，并在 Azure VM 上安装和验证 Cloudflare WARP 客户端，以实现零成本出站互联网访问。

这些步骤涉及 Cloudflare 账户权限，必须由持有账户凭证的人员手动执行，无法自动化。

## 前置条件

- 拥有 Cloudflare Zero Trust 组织管理员权限
- Azure VM 当前具有公共 IP 或其他临时互联网路径（用于下载 WARP 客户端）
- 已准备好 GitHub 仓库的管理员权限（用于添加 Secrets）

---

## 步骤 1：在 Cloudflare Zero Trust 创建 Service Token

1. 打开浏览器，访问 [Cloudflare 仪表盘](https://dash.cloudflare.com)。
2. 使用管理员账户登录。
3. 在左侧导航栏选择 **Zero Trust**。
   - 若首次进入 Zero Trust，可能需要选择组织名称（Team name），按提示完成初始化。
4. 在 Zero Trust 控制台左侧导航栏，选择 **Access** → **Service Tokens**。
5. 点击页面右上角的 **Create Service Token** 按钮。
6. 输入 Token 名称，如 `aicbc-azure-vm-warp`。
7. 点击 **Create**。
8. 页面会显示 **Client ID** 和 **Client Secret**。
   - **重要**：Client Secret 只在此页面显示一次，离开页面后无法再次查看。请立即复制并保存到密码管理器。
9. 记录 **Client ID** 和 **Client Secret**，后续步骤需要用到。

**验证标准**：在 Cloudflare Zero Trust → Access → Service Tokens 列表中能看到名为 `aicbc-azure-vm-warp` 的 token。

---

## 步骤 2：配置 Device Enrollment Policy

1. 在 Cloudflare Zero Trust 控制台左侧导航栏，选择 **Settings** → **WARP Client**。
2. 点击 **Device Enrollment** 标签页。
3. 点击 **Create a policy** 或 **Add a policy** 按钮。
4. 填写策略信息：
   - **Policy Name**: `aicbc-azure-vm-enrollment`
   - **Action**: 选择 **Service Auth**
   - **Include**: 选择 **Service Token**，然后选择步骤 1 中创建的 token（`aicbc-azure-vm-warp`）
5. 点击 **Save**。

**验证标准**：在 Device Enrollment Policies 列表中能看到新添加的策略，且该策略的 Action 为 Service Auth，包含正确的 service token。

---

## 步骤 3：保存 Secrets 到 GitHub

1. 打开浏览器，访问 GitHub 仓库页面：`https://github.com/fromwordimport/ai_cbc`。
2. 点击顶部导航栏的 **Settings**。
3. 在左侧导航栏选择 **Secrets and variables** → **Actions**。
4. 依次创建以下三个 repository secret：

| Secret Name | 值 | 说明 |
|-------------|-----|------|
| `CF_WARP_ORG` | 你的 Cloudflare Zero Trust 团队名称（组织名称） | 即登录 Zero Trust 时使用的 team name |
| `CF_WARP_CLIENT_ID` | 步骤 1 中复制的 Client ID | Service Token 的公开标识符 |
| `CF_WARP_CLIENT_SECRET` | 步骤 1 中复制的 Client Secret | Service Token 的密钥 |

**验证标准**：在 GitHub 仓库 Settings → Secrets and variables → Actions 页面能看到 `CF_WARP_ORG`、`CF_WARP_CLIENT_ID`、`CF_WARP_CLIENT_SECRET` 三个条目。

---

## 步骤 4：在 Azure VM 上执行 WARP 安装脚本

**前提**：VM 必须暂时具有公共 IP 或其他互联网路径，以便下载 WARP 客户端。

1. 通过 SSH 登录到 Azure VM。
2. 确保已克隆项目仓库或已将 `scripts/setup-warp.sh` 复制到 VM 上。
3. 设置环境变量：

   ```bash
   export CF_WARP_ORG=your-team-name
   export CF_WARP_CLIENT_ID=xxx
   export CF_WARP_CLIENT_SECRET=yyy
   ```

4. 执行安装脚本：

   ```bash
   bash scripts/setup-warp.sh
   ```

   脚本会自动完成以下操作：
   - 检查 WARP 是否已安装，若未安装则添加 Cloudflare APT 仓库并安装 `cloudflare-warp` 包
   - 生成 MDM 配置文件 `/var/lib/cloudflare-warp/mdm.xml`，包含 service token 和组织信息
   - 启用并启动 `warp-svc` 服务
   - 执行 `warp-cli connect` 建立连接

**验证标准**：脚本执行完毕，终端输出 `WARP 已启动`。

---

## 步骤 5：验证 WARP 已激活

执行以下命令：

```bash
curl https://www.cloudflare.com/cdn-cgi/trace
```

**预期输出**：响应内容中包含 `warp=on`。

示例输出片段：
```
fl=xxx
h=www.cloudflare.com
ip=xxx.xxx.xxx.xxx
ts=xxx.xxx
colo=XXX
sn=xxx
warp=on
gateway=off
```

**验证标准**：`curl` 输出中明确包含 `warp=on`。

---

## 步骤 6：确保 Docker 出网走 WARP

测试 Docker 是否能通过 WARP 访问互联网：

```bash
docker pull hello-world
docker run --rm --network host hello-world
```

**预期结果**：镜像拉取成功，容器运行并输出 `Hello from Docker!`。

### 故障排查：Docker 未走 WARP

如果 `docker pull` 失败，按以下步骤排查：

1. **检查默认路由**：

   ```bash
   ip route | grep default
   ```

   确认默认路由指向 WARP 虚拟接口（如 `warp0` 或 `CloudflareWARP`）。

2. **尝试使用 host 网络模式**：

   ```bash
   docker run --rm --network host hello-world
   ```

   如果 host 模式成功但默认 bridge 模式失败，说明 Docker 网桥未继承 WARP 路由。

3. **解决方案选项**：

   - **方案 A：配置 Docker 使用系统代理**

     若 WARP 暴露了 SOCKS5 代理（如 `127.0.0.1:8080`），可在 `/etc/docker/daemon.json` 中配置：

     ```json
     {
       "proxies": {
         "http-proxy": "http://127.0.0.1:8080",
         "https-proxy": "http://127.0.0.1:8080"
       }
     }
     ```

     然后重启 Docker：`sudo systemctl restart docker`。

   - **方案 B：调整 iptables 使 Docker 网桥流量走 WARP**

     检查 WARP 接口名称：`ip link show | grep -i warp`
     然后添加 iptables 规则，将 Docker 网桥出站流量转发到 WARP 接口：

     ```bash
     sudo iptables -t nat -A POSTROUTING -o docker0 -j MASQUERADE
     sudo iptables -A FORWARD -i docker0 -o warp0 -j ACCEPT
     sudo iptables -A FORWARD -i warp0 -o docker0 -m state --state RELATED,ESTABLISHED -j ACCEPT
     ```

     （请将 `warp0` 替换为实际的 WARP 接口名称。）

   - **方案 C：使用 `--network host` 运行所有需要出网的容器**

     对于 `cloudflared` 等关键容器，已在 `scripts/setup-cloudflared.sh` 中使用 `--network host`，可直接继承 WARP 路由。

**验证标准**：`docker pull hello-world` 和 `docker run --rm --network host hello-world` 均成功执行。

---

## 步骤 7：解绑公共 IP 并重新验证

确认 WARP 和 Docker 均正常工作后：

1. 在 Azure 门户中解绑并删除 VM 的公共 IP。
2. 重新运行出站验证脚本：

   ```bash
   bash scripts/verify-outbound.sh
   ```

   该脚本会测试：
   - Cloudflare HTTPS 连通性
   - Docker Hub 镜像拉取
   - GitHub 仓库访问

**验证标准**：`scripts/verify-outbound.sh` 输出 `PASS: 默认出站访问可用`。

---

## 回滚信息

若需要回滚到公共 IP 方案：
1. 在 Azure 门户重新绑定原有的公共 IP。
2. 停止 WARP 服务：`sudo systemctl stop warp-svc`。
3. 可选：卸载 WARP：`sudo apt remove -y cloudflare-warp`。
4. 重新运行 `scripts/verify-outbound.sh` 确认公共 IP 出站正常。

---

> **注意**：本手册中的 `your-team-name` 和 `xxx`/`yyy` 仅为占位符，实际操作时请替换为真实的 Cloudflare Zero Trust 组织名称和 Service Token 凭证。

> **平台限制**：WARP 客户端官方支持 Debian/Ubuntu 系列 Linux 发行版。本脚本专为 **Azure B2ats v2 Linux VM** 设计，**不支持 Windows 环境**。
