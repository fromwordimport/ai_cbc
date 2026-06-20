# 虚拟消费者批量生成进度反馈设计

> **版本**：v1.0
> **日期**：2026-06-20
> **负责人**：小前（前端）、小应（LLM 应用）
> **状态**：方案 A 已实施；方案 B/C 待后续迭代

---

## 一、背景与问题

当前 `/api/v1/personas/generate` 为**同步接口**：前端发送请求后，后端按顺序完成所有画像的 4 层画像生成 + 辅助信息生成 + 真实性评分 + 偏见审计（含重试），最后一次性返回结果。

在 Azure B2ats v2（1 GiB RAM）+ DeepSeek 等第三方 API 场景下：
- 单个画像约触发 5-8 次 LLM 调用
- 单次 LLM 调用耗时 3-10 秒
- 生成 1 个画像约 30-90 秒，生成 10 个画像可能超过 5 分钟

前端原有 60 秒 axios timeout 极易触发 `timeout of 60000ms exceeded`，用户体验差。

---

## 二、目标

1. 避免大量生成时前端超时
2. 让用户感知生成进度，减少焦虑
3. 不阻塞用户继续浏览其他页面
4. 控制 B2ats v2 小内存 VM 上的并发与连接占用

---

## 三、方案 A：限制单次数量 + 延长超时 + 提示文案（已实施）

### 3.1 实现要点

- 前端批量生成弹窗：
  - 默认数量从 10 改为 **2**
  - `max` 限制为 **5**
  - 增加说明文案："单次建议 1-3 个，最多 5 个。大量生成请分多次操作，每个画像需要多次 LLM 调用，耗时约 30-90 秒。"
  - 增加 Alert："当前为同步生成：前端会保持连接等待后端完成。若网络不稳定或生成数量较多，仍可能超时，建议少量多次。"
- 前端 axios timeout 从 60 秒延长至 **10 分钟**
- Nginx `proxy_read_timeout` 从 120 秒延长至 **300 秒**

### 3.2 优点

- 改动最小，无后端改动
- 立即可用，缓解超时问题
- 适合当前 1-3 人 demo 场景

### 3.3 缺点

- 仍是同步阻塞，用户必须等待
- 无法看到实时进度
- 大量生成仍需多次点击

---

## 四、方案 B：异步批量生成 + 前端轮询（推荐后续迭代）

### 4.1 架构

```
前端                    后端
 |                       |
 |-- POST /personas/generate-async -->
 |                       | 创建 job_id，启动后台任务
 |<-- 202 {job_id} ------|
 |                       |
 |-- GET /personas/generate/{job_id}/status -->
 |<-- 200 {status, generated, total, current_persona_id} --|
 |                       |
 |-- (轮询直到 completed/failed) -->
```

### 4.2 后端改动

新增路由（`src/aicbc/api/routes/personas.py`）：

```python
@router.post("/personas/generate-async", status_code=202)
async def generate_personas_async(request: BatchGenerateRequest):
    job_id = create_generation_job(request)
    background_tasks.add_task(run_generation_job, job_id)
    return {"job_id": job_id, "status": "pending"}

@router.get("/personas/generate/{job_id}/status")
async def get_generation_job_status(job_id: str):
    job = get_job(job_id)
    return {
        "job_id": job_id,
        "status": job.status,
        "requested": job.requested,
        "generated": job.generated,
        "failed": job.failed,
        "current_persona_index": job.current_index,
        "errors": job.errors,
    }
```

存储：
- 使用 Redis 存储 job 状态（已部署）
- 或使用 MongoDB 新增 `generation_jobs` collection

### 4.3 前端改动

- 批量生成弹窗点击"开始生成"后立即关闭
- 全局显示一个进度 Toast / 进度条："正在生成画像 3/10"
- 轮询间隔：2 秒
- 完成后刷新画像列表

### 4.4 优点

- 真正的异步，用户可继续操作
- 可显示真实进度
- 不受前端 timeout 限制
- 后端可控并发，适合小内存 VM

### 4.5 缺点

- 后端改动较大
- 需要 job 状态持久化
- 需要处理任务失败、重试、清理

---

## 五、方案 C：Server-Sent Events 实时推送

### 5.1 架构

```
前端                    后端
 |-- GET /personas/generate-stream?study_id=xxx&count=10 -->
 |                       | 启动生成
 |<-- event: progress    |
 |<-- event: progress    |
 |<-- event: complete    |
```

### 5.2 后端改动

新增 SSE endpoint：

```python
@router.get("/personas/generate-stream")
async def generate_personas_stream(
    study_id: str,
    count: int,
    queue: asyncio.Queue,
):
    async def event_generator():
        for i in range(count):
            persona = await generate_one_persona(study_id, i)
            yield f"event: progress\ndata: {json.dumps({'index': i, 'total': count, 'persona_id': persona.persona_id})}\n\n"
        yield f"event: complete\ndata: {json.dumps({'generated': count})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 5.3 前端改动

- 使用 `EventSource` 接收后端推送
- 实时更新进度条
- 完成后刷新列表

### 5.4 优点

- 实时性最好
- 延迟最低
- 用户体验最佳

### 5.5 缺点

- SSE 在 Cloudflare Pages / Nginx 反向代理下需要额外配置（buffering、timeout）
- 长连接占用 B2ats v2 资源
- 失败恢复比轮询复杂
- 前端需处理断线重连

---

## 六、方案对比

| 维度 | 方案 A（已实施） | 方案 B（推荐） | 方案 C |
|------|------------------|----------------|--------|
| 实现复杂度 | 低 | 中 | 高 |
| 后端改动 | 无 | 中 | 中 |
| 前端改动 | 小 | 中 | 中 |
| 是否阻塞 | 是 | 否 | 否 |
| 真实进度 | 否 | 是 | 是 |
| 实时性 | 无 | 中（2s 轮询） | 高 |
| 失败恢复 | 简单 | 中 | 复杂 |
| 适合 demo | 是 | 是 | 是 |
| 适合生产 | 否 | 是 | 是 |

---

## 七、推荐路线

1. **当前阶段（demo）**：使用方案 A，限制单次 5 个以内，满足 1-3 人演示需求。
2. **下一阶段**：实现方案 B，改为异步批量生成 + 轮询，解决大量生成阻塞问题。
3. **未来可选**：在方案 B 稳定后，如需要更强实时性，再评估方案 C。

---

## 八、相关文件

- `frontend/src/pages/PersonaManager.tsx`
- `frontend/src/services/api.ts`
- `docker/nginx.azure-b2ats.conf`
- `src/aicbc/api/routes/personas.py`
- `src/aicbc/generators/profile_generator.py`
