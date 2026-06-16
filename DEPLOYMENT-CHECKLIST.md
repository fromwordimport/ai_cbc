# AI_CBC 低成本 Render 部署准备清单

> **方案**：Render + MongoDB Atlas + Upstash Redis + Cloudflare 子域名
> **适用场景**：个人/小团队，90% 时间仅 1 人访问
> **预估月成本**：¥0-50（仅 LLM API 调用费用）
> **日期**：2026-06-16
>
> **注意**：Render 免费计划仅支持 `web` 服务，不支持 `worker` 服务。本项目通过 `supervisord` 在单个 web 容器内同时运行 API、Celery Worker 和 Celery Beat。

---

## 一、前置条件

- [x] GitHub 仓库已创建：`https://github.com/fromwordimport/ai_cbc`
- [x] 代码已 push 到 `master` 分支
- [x] 拥有一个 Cloudflare 管理的域名： `fromworldimport.com`
- [x] 已阅读 `render.yaml` 部署配置

---

## 完成状态

- [x] Render `aicbc-api` web service 部署成功
- [x] MongoDB Atlas 连接成功
- [x] Upstash Redis 连接成功
- [x] Celery Worker / Beat 运行正常
- [x] Cloudflare 子域名 `aicbc-api.fromworldimport.com` 绑定成功
- [x] HTTPS 健康检查通过：`curl https://aicbc-api.fromworldimport.com/health`

### 2.1 Render（容器托管）

1. 访问 https://render.com
2. 使用 GitHub 账号登录
3. 完成邮箱验证

### 2.2 MongoDB Atlas（免费数据库）

1. 访问 https://www.mongodb.com/cloud/atlas
2. 注册账号并创建 Free Tier (M0) 集群
3. 创建数据库用户 `aicbc`
4. 配置 Network Access：
   - 临时方案：允许所有 IP (`0.0.0.0/0`)
   - 安全方案：仅允许 Render 出口 IP（Render 文档中查询）
5. 记录连接字符串，格式：
   ```
   mongodb+srv://aicbc:password@cluster0.xxxxx.mongodb.net/aicbc?retryWrites=true&w=majority
   ```

### 2.3 Upstash Redis（免费缓存/队列）

1. 访问 https://upstash.com
2. 使用 GitHub 账号登录
3. 创建新的 Redis 数据库
4. 选择 region 尽量靠近 Render 部署区域（如 Singapore / Oregon）
5. 记录 `UPSTASH_REDIS_REST_URL` 和 `UPSTASH_REDIS_REST_TOKEN`
6. 同时记录 Redis 协议连接串（Celery 需要）：
   ```
   redis://default:password@host.upstash.io:6379
   ```
   如果 Upstash 仅提供 REST/TLS，需要确认 Celery 是否支持 TLS Redis URL。

---

## 三、部署到 Render

### 3.1 创建 Blueprint

1. 在 Render Dashboard 点击 **New +**
2. 选择 **Blueprint**
3. 选择 GitHub 仓库 `fromwordimport/ai_cbc`
4. Render 自动读取 `render.yaml`

### 3.2 配置环境变量

Render 为 `aicbc-api` service 创建后，在 Dashboard 中填入以下 secret 值：

| Service | 变量名 | 来源 |
|---------|--------|------|
| aicbc-api | `MONGODB_URL` | MongoDB Atlas 连接串 |
| aicbc-api | `REDIS_URL` | Upstash Redis URL |
| aicbc-api | `ANTHROPIC_API_KEY` | Anthropic Console 或国内大模型平台 |
| aicbc-api | `OPENAI_API_KEY` | OpenAI Platform 或国内大模型平台 |
| aicbc-api | `SECRET_KEY` | Render 自动生成，无需修改 |

> **注意**：`SECRET_KEY` 由 Render 在 `aicbc-api` 中自动生成。由于 Render 免费计划不支持单独的 `worker` 服务，Celery Worker 和 Celery Beat 通过 `docker/supervisord-render.conf` 与 API 运行在同一个容器内，因此无需额外配置 worker/beat 服务。

### 3.3 验证部署

1. 等待 aicbc-api Build & Deploy 完成
2. 访问 Render 分配的域名：`https://aicbc-api.onrender.com`
3. 测试健康检查：
   ```bash
   curl https://aicbc-api.onrender.com/health
   ```
4. 在 Render Dashboard → aicbc-api → Logs 中确认：
   - FastAPI 已启动并监听 `0.0.0.0:8000`
   - Celery Worker 已连接 Redis 并等待任务
   - Celery Beat 已启动调度器

---

## 四、配置 Cloudflare 子域名

### 4.1 获取 Render 域名

在 Render Dashboard → aicbc-api → Settings 中找到默认域名，例如：
```
aicbc-api.onrender.com
```

本项目实际绑定的自定义域名为：
```
aicbc-api.fromworldimport.com
```

### 4.2 添加 DNS 记录

1. 登录 Cloudflare Dashboard
2. 选择你的域名 `fromworldimport.com`
3. 进入 DNS → Records
4. 添加 CNAME 记录：
   - **Type**: CNAME
   - **Name**: `aicbc-api`
   - **Target**: `aicbc-api.onrender.com`
   - **Proxy status**: 开启（橙色云图标）
   - **TTL**: Auto

### 4.3 在 Render 绑定自定义域名

**方式 A（推荐）**：`render.yaml` 中已配置 `domains: [aicbc-api.fromworldimport.com]`，push 后 Render 自动处理。

**方式 B（手动）**：
1. Render Dashboard → aicbc-api → Settings → Custom Domain
2. 输入 `aicbc-api.fromworldimport.com`
3. 等待 Render 验证 DNS（通常几分钟）
4. 开启 SSL（Render 自动签发 Let's Encrypt）

> 如果 Render 验证失败，先临时关闭 Cloudflare Proxy（改为灰色云 DNS only），验证通过后再开启 Proxy。

### 4.4 测试

```bash
nslookup aicbc-api.fromworldimport.com
curl https://aicbc-api.fromworldimport.com/health
curl https://aicbc-api.fromworldimport.com/ready
```

---

## 五、可选：配置 GitHub Actions 自动部署

Render Blueprint 会在每次 push 到 master 时自动重新部署，无需额外配置。

如需手动触发，可在 Render Dashboard 点击 **Manual Deploy**。

---

## 六、注意事项与限制

| 项目 | 说明 |
|------|------|
| **单容器运行所有进程** | Render free 不支持 worker，API / Worker / Beat 由 supervisord 在同一容器运行 |
| **免费 Web Service 休眠** | Render free web service 15 分钟无访问会休眠，下次请求唤醒约 30 秒；休眠期间 Celery 也停止运行 |
| **MongoDB Atlas M0 限制** | 512MB-5GB 存储，共享 CPU，适合个人开发 |
| **Upstash Redis 免费额度** | 每日 10,000 条命令，个人使用足够 |
| **Celery + Upstash TLS** | 如 Upstash 仅提供 TLS Redis，需确认 Celery 配置支持 `rediss://` |
| **大样本分析** | Render free 容器内存有限，大样本 HB 分析可能 OOM，需降低并发 |
| **K8s 方案保留** | `k8s/overlays/minimal/` 仍保留，未来流量增长时可迁移回 K8s |

---

## 七、回滚与调试

### 查看日志

```bash
# Render CLI（可选安装）
render logs --service aicbc-api
```

或在 Render Dashboard → aicbc-api → Logs 中查看。同一个日志流会包含 API、Worker、Beat 的输出。

### 本地调试容器

```bash
docker build -f docker/Dockerfile -t aicbc:test .
docker run -p 8000:8000 --env-file .env aicbc:test
```

---

## 八、与 K8s 方案的关系

| 方案 | 适用阶段 | 月成本 |
|------|---------|--------|
| **Render + Atlas + Upstash** | 当前个人使用 | ¥0-50 |
| `k8s/overlays/minimal/` | 未来 10+ 用户或需要稳定服务 | ¥50-100 |
| `k8s/overlays/staging/` | 正式 Staging 环境 | ¥500+ |

---

*完成本清单后，AI_CBC 后端即可通过 Cloudflare 子域名对外提供个人访问。*
