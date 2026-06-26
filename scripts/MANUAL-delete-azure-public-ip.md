# MANUAL: 删除 Azure 公共 IP

> **用途**：在确认 Cloudflare Tunnel 稳定运行且 CI/CD 正常后，安全删除 Azure 公共 IP 资源以节省成本。
> **前提**：Task 5（部署 cloudflared 并切换 DNS）已完成且验证通过。
> **风险等级**：中 — 删除后若 Tunnel 或 DNS 异常，将失去外部访问入口。请严格按 checklist 执行。

> **占位符说明**：本文档中所有 `api.example.com` 均为占位符，执行前必须替换为实际子域名。

> **DNS TTL 提醒**：迁移前应将 DNS TTL 降至 300 秒或更低；删除操作须等待旧 TTL 过期后再执行，以避免缓存解析问题。

---

## 前置确认（必须全部通过方可继续）

- [ ] **1. Cloudflare Tunnel 已连续稳定运行 >= 24 小时**

  验证方式（在 Azure VM 上执行）：
  ```bash
  bash scripts/check-tunnel.sh
  ```
  Expected：输出包含 `Registered tunnel connection`，容器状态为 `Up`，无频繁重连或错误日志。

  另从外部任意机器验证：
  ```bash
  curl -I https://api.example.com/health
  ```
  Expected：HTTP 200，连续多次请求均成功。

- [ ] **2. 至少一次 CI/CD 部署成功**

  验证方式：
  - 查看 GitHub Actions 最近的一次**最近的生产部署 workflow**（或等效部署 workflow）运行记录，状态为绿色通过。
  - 或查看 Azure VM 上的应用版本与最新提交一致。

- [ ] **3. 确认公共 IP 无剩余依赖**

  在 Azure 门户中：
  1. 进入 **公共 IP 地址** 资源页。
  2. 查看 **关联到** 或 **依赖项** 面板。
  3. 确认该公共 IP 未绑定到任何：
     - 网络接口 (NIC)
     - 负载均衡器 (Load Balancer)
     - NAT 网关
     - 应用网关 (Application Gateway)
     - 防火墙
  4. 若存在任何依赖，**禁止删除**，先解除绑定。

---

## 删除操作

- [ ] **4. 在 Azure 门户删除公共 IP 资源**

  1. 导航至该公共 IP 资源页。
  2. 再次确认 **关联到** 为空。
  3. 点击 **删除**（Delete）。
  4. 在确认对话框中输入公共 IP 名称，确认删除。
  5. 等待删除完成，确认资源列表中不再显示该公共 IP。

---

## 删除后验证

- [ ] **5. 服务访问不受影响**

  删除后立即从外部验证：
  ```bash
  curl -I https://api.example.com/health
  nslookup api.example.com
  ```
  Expected：
  - `curl` 仍返回 HTTP 200。
  - `nslookup` 仍解析到 Cloudflare（CNAME 至 `*.cfargotunnel.com`）。

- [ ] **6. 下一张 Azure 账单确认费用为 0**

  1. 等待下一个计费周期（或 24–48 小时后查看成本分析）。
  > **注意**：Azure Cost Analysis 通常在数小时内即可显示按小时计费的变化，无需等待完整计费周期结束。
  2. 在 Azure Cost Management + Billing 中筛选 **公共 IP 地址** 资源。
  3. 确认该公共 IP 的计费为 0，或资源已不在账单中。

---

## 回滚说明

> **警告**：如果在删除前或删除后发现任何异常（Tunnel 断开、DNS 解析失败、CI/CD 无法部署），**立即停止**并执行回滚。

回滚步骤参考 Task 5 回滚方案：

1. **停止 cloudflared**（如需）：
   ```bash
   docker stop cloudflared && docker rm cloudflared
   ```
2. **重新创建 Azure 公共 IP**（如已删除）：
   - 在 Azure 门户中重新创建同名公共 IP（标准 SKU，静态分配）。
   - 若因 Azure 元数据保留导致同名 IP 创建失败，请使用不同名称创建新 IP，并同步更新 DNS A 记录。
   - 将其绑定到原 VM 的网络接口（NIC）。
3. **切换 DNS 回 A 记录**：
   - 在 Cloudflare DNS 中，将 `api.example.com` 从 CNAME 改回 A 记录。
   - 目标地址填写重新创建的 Azure 公共 IP。
   - Proxy 状态：按需启用或禁用。
4. **验证外部访问**：
   ```bash
   curl -I https://api.example.com/health
   ```
   Expected：HTTP 200。
5. **排查 Tunnel 问题**：
   - 查看 `scripts/check-tunnel.sh` 输出。
   - 检查 `CF_TUNNEL_TOKEN` 是否有效。
   - 确认 Cloudflare 网络状态页无区域性故障。

---

## 完成签名

| 项目 | 执行人 | 日期 | 备注 |
|------|--------|------|------|
| 前置确认通过 | | | |
| 公共 IP 删除 | | | |
| 删除后验证通过 | | | |
| 账单确认 | | | |

---

> **文档版本**：v1.0  
> **关联任务**：Task 6（删除 Azure 公共 IP）→ 依赖 Task 5（Cloudflare Tunnel 部署与 DNS 切换）
