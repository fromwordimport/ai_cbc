# Azure VM 默认出站访问验证 — 手动操作指南

> **用途**：在移除 Azure VM 公共 IP 前，验证 VM 是否仍具备互联网出网能力。  
> **前提**：拥有 Azure 门户访问权限，且 VM 当前绑定了公共 IP。  
> **风险**：操作可回滚 — 本指南只「解绑」公共 IP，不删除资源。

---

## 0. 降低 DNS TTL（如目标域名指向该公共 IP）

如果计划后续将域名解析迁移至 Cloudflare Tunnel（Task 5），在解绑公共 IP 之前应先降低 DNS TTL：

1. 登录域名 DNS 服务商控制台。
2. 找到指向该 VM 公共 IP 的子域名记录。
3. 将 TTL 修改为 **300 秒或更低**（例如 60 秒）。
4. **等待旧 TTL 过期**后再继续下一步（例如旧 TTL 为 3600 秒，则需等待至少 1 小时）。

> **注意**：TTL 未过期时，全球 DNS 缓存仍可能解析到旧公共 IP，导致切换后部分用户无法访问。

---

## 1. 临时解绑公共 IP（Azure 门户）

1. 登录 [Azure 门户](https://portal.azure.com)。
2. 导航至目标虚拟机（VM）。
3. 左侧菜单选择 **Networking** → 点击网络接口名称。
4. 选择 **IP configurations**。
5. 点击当前公共 IP 配置项，将 **Public IP address** 下拉框改为 **None**。
6. 点击 **Save**。公共 IP 资源本身保留在订阅中，仅与 VM 断开关联。

> **注意**：解绑后，SSH 直连公共 IP 会立即失效。请提前确认下一步的登录方式。

---

## 2. 登录 VM（无公共 IP 方式）

选择以下任一方式：

- **Azure Serial Console**（推荐）：  
  VM 页面 → **Help** → **Serial console**。基于 Azure 管理平面，不依赖公共 IP。
- **Azure Bastion**：这是 Azure 的付费服务；如果当前已部署且费用可接受，可临时使用；否则优先使用 Serial Console。
- **其他私有通道**：如已有 VPN、ExpressRoute、或另一台同 VNet 的跳板机。

---

## 3. 运行验证脚本

在 VM 内执行：

```bash
bash scripts/verify-outbound.sh
```

---

## 4. 解读输出

| 输出 | 含义 | 下一步 |
|---|---|---|
| `PASS: 默认出站访问可用` | VM 在无公共 IP 时仍能正常出网 | 继续 **Task 5**（部署 cloudflared 并切换 DNS） |
| `FAIL: 无法访问 https://cloudflare.com` | 基础 HTTPS 出网失败 | 执行 **回滚**（见第 5 节） |
| `FAIL: 无法从 Docker Hub 拉取镜像` | Docker Hub 不可达 | 执行 **回滚** |
| `FAIL: 无法 fetch GitHub` | Git 仓库同步失败 | 执行 **回滚** |

---

## 5. 回滚操作（验证失败时）

如果任何一项测试失败，说明当前 Azure 订阅/区域已禁用「默认出站访问」，0 成本方案的前提不成立：

1. 返回 Azure 门户 → VM → **Networking** → **IP configurations**。
2. 将 **Public IP address** 重新绑定为原来的公共 IP 资源。
3. 保存后等待 30 秒，确认 SSH/Serial Console 中可再次 `curl -I https://cloudflare.com`。
4. 不要继续 Task 5。改为先执行 **Task 4**（配置 Cloudflare WARP/One 作为免费出站 fallback）。
5. WARP 配置完成并重新解绑公共 IP 后，再次运行本脚本验证。

---

## 6. 快速检查清单

- [ ] 已确认 Azure 门户可正常访问。
- [ ] 已记录当前公共 IP 资源的名称（解绑后方便重新绑定）。
- [ ] 已通过 Serial Console 或其他非公共 IP 方式登录 VM。
- [ ] 已运行 `bash scripts/verify-outbound.sh` 并记录完整输出。
- [ ] 根据 PASS/FAIL 结果，决定继续 Task 5 或回滚后执行 Task 4。

---

> **版本**：v1.0  
> **日期**：2026-06-26  
> **负责人**：小维（DevOps/MLOps）
