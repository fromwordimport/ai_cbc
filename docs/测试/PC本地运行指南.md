# AI_CBC PC 本地运行指南

> **版本**：v1.0  
> **日期**：2026-06-13  
> **用途**：指导开发/测试人员在 PC 本地（Windows 11）启动并运行 AI_CBC 完整系统  
> **维护者**：小培（培训工程师）

---

## 目录

1. [前置条件](#1-前置条件)
2. [环境准备](#2-环境准备)
3. [启动后端（Mock 模式）](#3-启动后端mock-模式)
4. [启动前端](#4-启动前端)
5. [验证系统运行](#5-验证系统运行)
6. [常见问题排查](#6-常见问题排查)
7. [附录：后端 API 端点清单](#7-附录后端-api-端点清单)

---

## 1. 前置条件

### 1.1 硬件要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| 操作系统 | Windows 10/11 | Windows 11 Pro |
| 内存 | 8 GB | 16 GB |
| 磁盘空间 | 2 GB 可用空间 | 5 GB 可用空间 |
| 网络 | 本地回环即可 | 本地回环即可 |

### 1.2 软件依赖

| 软件 | 版本 | 用途 | 验证命令 |
|------|------|------|---------|
| Python | 3.11+ | 后端运行 | `python --version` |
| Node.js | 18.x+ | 前端构建 | `node --version` |
| npm | 9.x+ | 前端包管理 | `npm --version` |
| Git | 2.40+ | 代码管理 | `git --version` |

> **注意**：本项目使用 `uv` 进行 Python 环境管理（而非 pip/conda/poetry）。详见 `CLAUDE.md`。

---

## 2. 环境准备

### 2.1 克隆/进入仓库

```bash
# 如果尚未克隆
cd E:\machine_learning_study
# 仓库已存在，直接进入
cd E:\machine_learning_study\AI_CBC
```

### 2.2 初始化 Python 虚拟环境

```bash
# 使用 uv 创建虚拟环境（推荐）
uv venv .venv

# 或如果 .venv 已存在，直接激活
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Windows CMD:
.venv\Scripts\activate.bat
# Git Bash:
source .venv/Scripts/activate
```

### 2.3 安装前端依赖

```bash
cd E:\machine_learning_study\AI_CBC\frontend

# 如果 node_modules 已存在且完整，跳过
if (-not (Test-Path "node_modules")) {
    npm install
}
```

> **已知问题**：前端依赖已预装（`node_modules` 已存在），通常无需重新安装。

---

## 3. 启动后端（Mock 模式）

### 3.1 启动 Mock 后端

```bash
# 清理残留 Python 进程（PowerShell）
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

# 进入项目根目录
cd E:\machine_learning_study\AI_CBC

# 启动 mock 后端
.venv\Scripts\python scripts\dev_server_with_mocks.py
```

**期望输出：**

```
Starting AI_CBC dev server with mocked LLM on http://127.0.0.1:8000
Endpoints:
  GET  /api/v1/health
  GET  /api/v1/cost-status
  GET  /api/v1/studies
  ...
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

### 3.2 验证后端启动

```bash
# 新终端窗口
curl http://127.0.0.1:8000/api/v1/health
# 期望输出：{"status":"healthy","version":"0.1.0",...}
```

### 3.3 关于完整后端

> **当前状态**：完整后端（`uv run python -m aicbc.main`）因 pydantic Settings SECRET_KEY 校验错误（需 ≥32 字符）无法启动。Mock 后端已覆盖所有前端测试需求，包含：
>
> - 健康检查、成本状态
> - 研究管理（列表/详情/创建/删除）
> - 问卷生成与查看
> - 画像生成与管理（含 4 层数据）
> - 作答模拟与导出
> - HB 分析（含收敛诊断、属性重要性、WTP）
> - 市场模拟（含 by_segment）
> - 细分群体比较
> - 对话实验室

---

## 4. 启动前端

### 4.1 启动 Vite 开发服务器

```bash
# 新终端窗口（保持后端运行）
cd E:\machine_learning_study\AI_CBC\frontend
npm run dev
```

**期望输出：**

```
  VITE v5.4.0  ready in xxx ms

  ➜  Local:   http://localhost:3000/
  ➜  Network: use --host to expose
  ➜  press h + enter to show help
```

> **端口漂移说明**：`vite.config.ts` 中默认端口为 3000。若 3000 已被占用，Vite 会自动漂移（如 3001、3002），请以终端实际输出为准。后端 CORS 已同时允许 `localhost:3000` 和 `localhost:3001`，无需修改后端即可访问。

### 4.2 前端配置说明

前端通过 Vite 代理将 `/api` 请求转发到后端：

```typescript
// frontend/vite.config.ts
server: {
  port: 3000,
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
}
```

> **无需修改**：代理配置已正确设置，前端可直接访问后端 API。

---

## 5. 验证系统运行

### 5.1 浏览器验证

打开浏览器访问以下地址：

| URL | 期望结果 | 验证项 |
|-----|---------|--------|
| `http://localhost:3000` 或实际漂移端口（如 `3001`） | 总览页面加载 | 左侧菜单、统计卡片 |
| `http://127.0.0.1:8000/api/v1/health` | JSON 响应 | 后端健康状态 |
| `http://127.0.0.1:8000/docs` | Swagger UI | API 文档完整性 |

### 5.2 快速功能验证（curl）

```bash
# 1. 获取研究列表
curl -s http://127.0.0.1:8000/api/v1/studies | head -c 200

# 2. 获取问卷详情
curl -s http://127.0.0.1:8000/api/v1/studies/demo-study-001/questionnaire | head -c 200

# 3. 获取画像列表
curl -s http://127.0.0.1:8000/api/v1/personas | head -c 200

# 4. 获取成本状态
curl -s http://127.0.0.1:8000/api/v1/cost-status
```

### 5.3 端到端主链路验证

按照 `docs/测试/系统运行说明书.md` 执行：

1. 创建研究 `dishwasher-001`
2. 生成问卷（12 选择集 × 3 方案）
3. 生成 5 个虚拟消费者
4. 模拟作答（deterministic 模式）
5. 运行 HB 分析
6. 查看分析结果（属性重要性、收敛诊断、WTP）

> **详细步骤**：参见 `docs/测试/系统运行说明书.md` 第 2 章。

---

## 6. 常见问题排查

### 6.1 后端启动失败

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| `SECRET_KEY` 校验错误 | pydantic Settings 要求 ≥32 字符 | 使用 mock 后端：`scripts/dev_server_with_mocks.py` |
| `ModuleNotFoundError` | 依赖未安装 | 运行 `uv pip install -e .` |
| 端口 8000 被占用 | 其他进程占用 | `Get-Process python \| Stop-Process` 后重试 |
| 中文乱码 | 终端编码问题 | 使用 PowerShell 或设置 `chcp 65001` |

### 6.2 前端启动失败

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| `npm: command not found` | Node.js 未安装 | 安装 Node.js 18+ |
| `module not found` | 依赖缺失 | `cd frontend && npm install` |
| 端口 3000 被占用 | 其他进程占用 | 修改 `vite.config.ts` 中的 port，或关闭占用端口的进程 |
| 端口漂移 | 前后端端口与文档不一致 | 确认后端 `8000`、前端 `3000`，如有冲突按实际端口访问 |
| 代理失败 | 后端未启动 | 先启动后端，再启动前端 |

### 6.3 API 请求失败

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| 404 Not Found | 端点不存在 | 检查 URL 路径 |
| 400 Bad Request | 请求体格式错误 | 检查 Content-Type 和 JSON 格式 |
| 网络连接失败 | 后端未启动 | 启动后端并检查端口 |
| CORS 错误 | 跨域问题 | 确认前端代理配置正确 |

### 6.4 创建研究返回 400

**问题**：直接通过 curl 发送中文 JSON 时，POST `/api/v1/studies` 返回 `{"detail":"There was an error parsing the body"}`。

**原因**：可能是中文编码或请求头问题。

**解决方案**：
1. 通过前端表单提交（推荐）
2. 使用 PowerShell 的 `Invoke-RestMethod` 而非 curl
3. 确保请求头包含 `"Content-Type: application/json; charset=utf-8"`
4. 使用预置研究 `demo-study-001` 进行测试

---

## 7. 附录：后端 API 端点清单

### 7.1 健康与监控

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/cost-status` | 成本状态与熔断 |

### 7.2 研究管理

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/studies` | 研究列表 |
| POST | `/api/v1/studies` | 创建研究 |
| GET | `/api/v1/studies/{id}` | 研究详情 |
| DELETE | `/api/v1/studies/{id}` | 删除研究 |
| POST | `/api/v1/studies/{id}/generate` | 生成问卷 |
| GET | `/api/v1/studies/{id}/questionnaire` | 问卷详情 |

### 7.3 画像管理

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/personas` | 画像列表 |
| POST | `/api/v1/personas/generate` | 批量生成画像 |
| GET | `/api/v1/personas/{id}` | 画像详情 |
| GET | `/api/v1/personas/{id}/layers/{n}` | 获取第 n 层数据 |
| POST | `/api/v1/personas/{id}/converse` | 对话 |
| DELETE | `/api/v1/personas/{id}` | 删除画像 |

### 7.4 作答模拟

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/v1/studies/{id}/simulate-responses` | 模拟作答 |
| GET | `/api/v1/studies/{id}/responses/export` | 导出数据集 |

### 7.5 分析

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/v1/studies/{id}/analyze` | 运行 HB 分析 |
| GET | `/api/v1/studies/{id}/analysis/{aid}` | 分析结果 |
| GET | `/api/v1/studies/{id}/analysis/{aid}/status` | 分析状态 |
| GET | `/api/v1/studies/{id}/analysis/{aid}/importance` | 属性重要性 |
| GET | `/api/v1/studies/{id}/analysis/{aid}/convergence` | 收敛诊断 |
| GET | `/api/v1/studies/{id}/analysis/{aid}/wtp` | 支付意愿 |
| POST | `/api/v1/studies/{id}/analysis/{aid}/simulate-market` | 市场模拟 |
| GET | `/api/v1/studies/{id}/analysis/{aid}/segment-comparison` | 细分对比 |

---

> **相关文档**：
> - `docs/测试/系统运行说明书.md` — 详细测试步骤
> - `docs/测试/端到端验证报告.md` — 验证结果与问题记录
> - `CLAUDE.md` — 项目架构与开发规范
