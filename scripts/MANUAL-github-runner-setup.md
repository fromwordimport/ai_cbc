# GitHub Self-Hosted Runner 手动安装指南

## 概述

本文档说明如何在 Azure B2ats VM 上手动安装并注册 GitHub Actions self-hosted runner。

## 前置条件

- 已登录 Azure B2ats VM（通过 SSH 或串口控制台）。
- 具有 GitHub 仓库的 Admin 权限（用于生成 runner registration token）。
- `scripts/setup-github-runner.sh` 已存在于 `/opt/aicbc/scripts/`。

## 步骤 1：生成 GitHub Runner Registration Token

### 方式 A：通过 GitHub Web UI（推荐）

1. 打开浏览器，访问仓库页面：`https://github.com/fromwordimport/ai_cbc`
2. 点击顶部菜单 **Settings** → 左侧边栏 **Actions** → **Runners**
3. 点击右上角 **New self-hosted runner** 按钮
4. 在页面底部找到 **Authentication** 部分，复制 `token` 字段的值（形如 `AEXXXXX...` 的字符串）

### 方式 B：通过 GitHub API

在本地机器（有 `GITHUB_TOKEN` 环境变量）执行：

```bash
curl -X POST -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/fromwordimport/ai_cbc/actions/runners/registration-token
```

响应示例：

```json
{
  "token": "AEXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "expires_at": "2026-06-26T12:00:00.000Z"
}
```

复制 `token` 字段的值。

**注意：** registration token 有效期约 1 小时，过期后需重新生成。

## 步骤 2：设置环境变量

在 Azure VM 上执行：

```bash
export GITHUB_RUNNER_TOKEN="AEXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
```

可选：自定义 runner 名称（默认 `azure-b2ats`）或仓库：

```bash
export GITHUB_RUNNER_NAME="azure-b2ats"
export GITHUB_REPO="fromwordimport/ai_cbc"
```

## 步骤 3：运行安装脚本

```bash
cd /opt/aicbc
bash scripts/setup-github-runner.sh
```

脚本将自动：

1. 下载最新版 GitHub Actions runner（`actions/runner` releases）。
2. 解压到 `/opt/github-runner/`。
3. 使用 registration token 注册 runner，标签为 `self-hosted,azure-b2ats`。
4. 安装并启动 systemd 服务。

## 步骤 4：验证 Runner 状态

1. 返回 GitHub 仓库页面：`https://github.com/fromwordimport/ai_cbc`
2. 点击 **Settings** → **Actions** → **Runners**
3. 在列表中找到名为 `azure-b2ats`（或自定义名称）的 runner
4. 确认状态为 **Idle**（绿色图标）

也可在 VM 上检查服务状态：

```bash
sudo systemctl status actions.runner.fromwordimport-ai_cbc.azure-b2ats.service
```

## 步骤 5：测试 Runner（可选）

触发一次 workflow 运行（如手动触发 `cd-azure-b2ats`），确认 runner 能成功执行 job。

## 移除 Runner

如需卸载或迁移 runner，先在 VM 上执行：

```bash
cd /opt/github-runner
# 获取新的 removal token（与 registration token 相同流程，或从 GitHub UI 获取）
export TOKEN="AEXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
./config.sh remove --token "$TOKEN"
sudo ./svc.sh uninstall
```

然后从 GitHub UI 的 Runners 列表中确认该 runner 已消失。

## 故障排查

| 问题 | 可能原因 | 解决方式 |
|------|----------|----------|
| `GITHUB_RUNNER_TOKEN 未设置` | 环境变量未导出 | 确认 `export GITHUB_RUNNER_TOKEN=...` |
| `curl: (22) The requested URL returned error: 404` | 架构检测失败 | 手动检查 `uname -m` 输出 |
| `config.sh: 无法连接到 GitHub` | VM 无 outbound 网络 | 检查 WARP/Cloudflare 隧道状态 |
| runner 状态为 `Offline` | 服务未启动或网络中断 | `sudo systemctl restart actions.runner...` |

## 参考

- [GitHub Docs: Adding self-hosted runners](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners)
- [GitHub Docs: Removing self-hosted runners](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/removing-self-hosted-runners)
