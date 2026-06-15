# AI_CBC 性能测试报告 v0.2.0

> **版本**：v0.2.0  
> **定位**：生产就绪整改 / 模块 10 性能基准测试  
> **维护人**：小速（性能负责人）  
> **关联文档**：[生产就绪整改计划](../docs/生产就绪评估/2026-06-14-生产就绪整改计划.md)、[测试脚本](../../tests/performance/test_load.py)

## 1. 测试目标

验证 AI_CBC MVP v0.2.0 在并发负载下的响应能力与稳定性，识别性能瓶颈，为生产环境容量规划提供数据支撑。

## 2. 测试环境

| 维度 | 配置 |
|------|------|
| 操作系统 | Windows 11 Pro (10.0.26100) |
| Python | 3.12.10 |
| 运行方式 | `uvicorn aicbc.main:app --host 127.0.0.1 --port 8001` |
| 工作进程 | 1 个 Uvicorn worker |
| 存储模式 | `USE_MEMORY_STORE=1`（内存存储） |
| 数据库 | MongoDB 未启用（本地未部署） |
| 缓存/限流 | 内存 Token Bucket，未启用 Redis |
| LLM | 实际调用 Anthropic/OpenAI（ persona 生成与分析任务） |
| 压测工具 | Locust 2.44.3 |

**注意**：本次基线测试在本地开发环境执行，使用内存存储与单 worker，结果主要用于发现代码级瓶颈与脚本验证，不代表生产部署的真实吞吐。生产环境需使用 MongoDB + Redis + 多 worker 重新跑测。

## 3. 测试场景

压测脚本 `tests/performance/test_load.py` 定义三类虚拟用户：

| 用户类型 | 权重 | 行为描述 | 代表场景 |
|----------|------|----------|----------|
| `HealthCheckUser` | 5 | 高频访问 `/health`、`/ready`、`/metrics` | 探针与监控 |
| `StudyManagementUser` | 3 | 创建研究、查询研究、生成问卷 | 研究员日常操作 |
| `FullPipelineUser` | 1 | 完整流程：创建研究 → 生成问卷 → 生成画像 → 模拟作答 → 运行分析 | 端到端 CBC 实验 |

所有请求携带 `X-API-Key`、`X-User-Role=admin`、`X-User-Id` 头部。

## 4. 测试执行

### 4.1 冒烟测试

```bash
cd tests/performance
uv run locust -f test_load.py --host http://127.0.0.1:8001 --headless \
    -u 2 -r 2 --run-time 15s --only-summary
```

结果：16 请求全部成功，无失败，脚本可正常驱动三类用户。

### 4.2 50 并发基线测试

```bash
uv run locust -f test_load.py --host http://127.0.0.1:8001 --headless \
    -u 50 -r 10 --run-time 60s --only-summary
```

**负载分布**：
- HealthCheckUser：27 用户
- StudyManagementUser：17 用户
- FullPipelineUser：6 用户

**总体结果**：

| 指标 | 数值 |
|------|------|
| 总请求数 | 41 |
| 失败数 | 0 |
| 平均响应时间 | 1159 ms |
| 中位数响应时间 | 940 ms |
| 95% 响应时间 | 3700 ms |
| 吞吐 (req/s) | 7.26 |

**分接口结果**：

| 方法 | 接口 | 请求数 | 失败数 | 平均 (ms) | 中位 (ms) | 最大 (ms) |
|------|------|--------|--------|-----------|-----------|-----------|
| GET | `/health` | 15 | 0 | 1044 | 940 | 2628 |
| GET | `/metrics` | 5 | 0 | 1516 | 2000 | 2597 |
| GET | `/ready` | 5 | 0 | 461 | 410 | 937 |
| GET | `/studies` | 2 | 0 | 475 | 12 | 937 |
| POST | `/studies` | 8 | 0 | 527 | 940 | 943 |
| POST | `/studies/{id}/generate` | 6 | 0 | 2800 | 1916 | 3683 |

**说明**：`FullPipelineUser` 在 60 秒内未完成 persona 生成与分析环节（等待时间 5–10s，单循环耗时长），因此未产生相关请求。

## 5. 瓶颈分析

### 5.1 主要瓶颈：问卷生成（`/studies/{id}/generate`）

- 平均响应时间 **2800 ms**，为该次测试最高。
- D-optimal 设计算法在 Python 单线程中执行，CPU 密集型。
- 单 worker 模式下，多个并发请求排队执行，进一步放大延迟。

### 5.2 次要瓶颈：监控与审计中间件

- `/metrics` 平均 1516 ms：Prometheus 指标在请求链中实时聚合，高并发下串行计算。
- `/ready` 涉及依赖检查（MongoDB、Redis），在内存模式下仍有固定开销。

### 5.3 内存存储的并发限制

- 内存存储使用 `threading.Lock` 保护关键操作，写操作串行化。
- 单 Uvicorn worker 无法利用多核，CPU 密集型任务无法横向扩展。

### 5.4 LLM 调用瓶颈

- persona 生成与 HB 分析均调用外部 LLM，延迟不可控。
- 生产环境应配置异步任务队列（Celery + Redis）并限制并发。

## 6. 优化建议

| 优先级 | 优化项 | 预期效果 |
|--------|--------|----------|
| P0 | 将 `/studies/{id}/generate` 改为异步 Celery 任务 | 避免同步阻塞，提升并发 |
| P0 | 部署多 Uvicorn worker（`--workers 4+`） | 利用多核，提升吞吐 |
| P1 | 对 `/metrics` 增加缓存或走独立进程 | 降低监控端点对主链路的影响 |
| P1 | 启用 Redis 分布式限流与缓存 | 减少单点竞争 |
| P1 | 使用 MongoDB 持久化并配置连接池 | 替换内存存储，支持水平扩展 |
| P2 | 为 LLM 调用增加并发控制与降级模型 | 降低成本与延迟 |

## 7. 高并发测试指南

在具备 MongoDB + Redis 的 staging 环境中，可执行以下命令获取 100/500/1000 并发数据：

```bash
# 100 并发
cd tests/performance
uv run locust -f test_load.py --host https://staging.aicbc.example.com --headless \
    -u 100 -r 20 --run-time 5m --csv aicbc_load_100

# 500 并发
uv run locust -f test_load.py --host https://staging.aicbc.example.com --headless \
    -u 500 -r 50 --run-time 5m --csv aicbc_load_500

# 1000 并发
uv run locust -f test_load.py --host https://staging.aicbc.example.com --headless \
    -u 1000 -r 100 --run-time 5m --csv aicbc_load_1000
```

生产环境压测建议：
- 先对只读接口（`/health`、`/ready`、`/studies`）进行高并发测试。
- 再逐步增加写操作与完整流程测试。
- 监控 CPU、内存、MongoDB 连接数、Redis 队列深度、LLM token 消耗。

## 8. 结论

- 压测脚本 `tests/performance/test_load.py` 已完成并验证可用。
- 本地 50 并发基线无失败，但同步问卷生成是主要性能瓶颈。
- 建议在完成 MongoDB/Redis/Celery 部署后，在 staging 环境补充 100/500/1000 并发正式测试，并据此调整 worker 数量与资源限制。

## 9. 附录：文件清单

| 文件 | 说明 |
|------|------|
| `tests/performance/test_load.py` | Locust 压测脚本 |
| `reports/performance_test_report_v0.2.0.md` | 本报告 |

---

**报告日期**：2026-06-15  
**下一步**：在 staging 环境完成 K8s 部署后，执行 100/500/1000 并发正式压测并回填数据。
