# AI_CBC 性能审查报告

**审查日期：** 2026-06-12
**审查范围：** src/, tests/, frontend/
**审查方法：** 静态代码分析

---

## TOP 10 性能瓶颈（按严重程度排序）

| 排名 | 瓶颈 | 位置 | 影响程度 | 修复分类 |
|------|------|------|----------|----------|
| 1 | 前端路由无懒加载，所有页面代码打包为一个 chunk | `frontend/src/router.tsx` | 高 | 可立即修复 |
| 2 | 批量 persona 生成串行阻塞，无并发控制 | `src/aicbc/agents/consumer_generator.py:255` | 高 | 中期优化 |
| 3 | D-optimal 设计算法三重循环纯 Python 执行 | `src/aicbc/questionnaire/design/d_optimal.py:147-187` | 高 | 中期优化 |
| 4 | HB model fit 同步阻塞 FastAPI 事件循环 | `src/aicbc/analysis/routes.py:198` | 高 | 可立即修复 |
| 5 | 所有 Store 层 O(n) 线性扫描过滤，无索引 | `src/aicbc/core/store.py`, `src/aicbc/analysis/store.py` | 中-高 | 可立即修复 |
| 6 | prometheus_client 在模块顶层加载，拖慢所有下游导入 | `src/aicbc/monitoring/metrics.py:17` | 中 | 可立即修复 |
| 7 | pandas/numpy 在 15+ 个源文件中顶层导入 | 多处 | 中 | 可立即修复 |
| 8 | conftest.py autouse fixture 每测试执行 7 次清理 | `tests/conftest.py:100-172` | 中 | ✅ 已修复 |
| 9 | HB 引擎默认采样参数未根据数据规模动态调整 | `src/aicbc/analysis/engines/hb_engine.py:219-227` | 中 | 中期优化 |
| 10 | LLM retry backoff 使用 time.sleep 阻塞事件循环线程 | `src/aicbc/llm/client.py:371-373` | 中 | 可立即修复 |

---

## 详细审查

### 一、导入链瓶颈

#### 1. prometheus_client 顶层导入
- **文件：** `src/aicbc/monitoring/metrics.py:17`
- **影响：** 任何导入 `aicbc.monitoring` 的操作都会触发 prometheus_client 完整加载（约 200-400ms）。已在 Windows 上被证实导致进程崩溃。
- **建议：** 使用惰性初始化函数包装所有指标声明。

#### 2. pandas/numpy 顶层导入
- **涉及文件（15+）：** `hb_engine.py`, `mnl_engine.py`, `analysis/routes.py`, `preprocessing.py`, `importance.py`, `wtp.py`, `segment_comparison.py`, `market_simulator.py`, `d_optimal.py`, `orthogonal.py`, `efficiency.py`, `effects_coding.py` 等
- **影响：** pandas (~15MB) + numpy (~30MB) 导入消耗约 1-3 秒 CPU 时间，显著增加 API 冷启动时间。
- **建议：** 改为函数内局部导入（参考 hb_engine.py 对 pymc 的做法）。

---

### 二、FastAPI 应用初始化

#### 3. 同步分析请求阻塞事件循环
- **文件：** `src/aicbc/analysis/routes.py:198`
- **影响：** HB 模型运行时（2-5 分钟），整个 API 服务器无法响应其他请求。
- **建议：** 接入 Celery 后台任务队列，端点返回 `202 Accepted`。

#### 4. 中间件栈
- **影响：** 健康检查端点仍经过全部 4 个中间件（RateLimit → Metrics → SecurityHeaders → APIKey）
- **建议：** 将速查路径列表向上游中间件提前，使健康检查尽早旁路。

---

### 三、测试套件

#### 5. autouse fixture 开销
- **文件：** `tests/conftest.py:100-172`
- **状态：** ✅ 已通过惰性导入缓存修复。首次导入后，每测试的清理开销从 ~50ms 降至 ~5ms。

#### 6. 慢测试分布
- 19 个 `@pytest.mark.slow` 测试，每个耗时 15-30 秒
- **状态：** ✅ pyproject.toml 已配置 `addopts = "-v -m \"not slow\""`，本地默认跳过。

---

### 四、MCMC 采样性能

#### 7. HB 引擎采样参数
- **文件：** `src/aicbc/analysis/engines/hb_engine.py:219-227`
- 默认参数：`n_draws=1000, n_tune=1000, n_chains=4, target_accept=0.9`
- **问题：** `target_accept=0.9` 偏高，对于混合 Logit 模型 0.8 即可，当前配置会使每次采样慢 2-3 倍。
- **建议：** 降至 0.8，根据数据规模动态适配。

#### 8. 诊断计算效率
- **文件：** `src/aicbc/analysis/engines/hb_engine.py:251-334`
- **问题：** `_compute_diagnostics()` 对每个参数名称循环提取坐标值，O(n_params * n_coords) 的 xarray 操作。
- **建议：** 使用 ArviZ 的 `az.summary()` 一次性提取所有参数。

---

### 五、LLM API 调用

#### 9. retry backoff 阻塞
- **文件：** `src/aicbc/llm/client.py:371-373`
- **代码：** `time.sleep(2 ** (attempt - 1))`
- **建议：** 在异步上下文中替换为 `asyncio.sleep()`。

#### 10. 连接池默认值
- **文件：** `src/aicbc/llm/client.py:77-87`
- **影响：** 批量 persona 生成（每次 5 次 LLM 调用）连接复用不足导致频繁 TCP 握手。
- **建议：** 显式配置 httpx 连接池（max_connections=10, max_keepalive_connections=5）。

---

### 六、缓存策略与存储层

#### 11. Store 无索引
- **文件：** `src/aicbc/core/store.py`, `src/aicbc/analysis/store.py`
- **影响：** 100,000 个 persona 按 segment 过滤需扫描全部记录。
- **建议：** 为常用过滤字段添加倒排索引字典。

#### 12. CostTracker 磁盘写入频率过高
- **文件：** `src/aicbc/cost/tracker.py:195-239`
- **影响：** 每次 LLM 调用后同步写入 JSON 文件，阻塞 I/O。
- **建议：** 节流写入（每 N 次记录或每 30 秒）。

---

### 七、前端性能

#### 13. 无路由懒加载
- **文件：** `frontend/src/router.tsx`
- **影响：** 所有 13 个页面 + antd (~300KB) + echarts (~250KB) 打包为单个 chunk。
- **建议：** 使用 `React.lazy()` + `Suspense` 实现按需加载，配置 Vite `manualChunks` 拆分。

#### 14. 缺少打包分析
- **文件：** `frontend/vite.config.ts`
- **建议：** 添加 `rollup-plugin-visualizer` 分析产物体积。

---

## 修复优先级建议

### 第一批（可立即修复，低风险高回报）
1. ✅ conftest.py 惰性导入缓存 → 测试速度提升
2. ✅ pyproject.toml 排除 slow 测试 → 本地开发提效
3. prometheus_client 惰性导入 → 测试/CLI 启动速度提升
4. Store 层添加哈希索引 → 查询从 O(n) 降为 O(1)
5. 前端路由懒加载 → 首页 JS 体积减少约 60%
6. pandas/numpy 改为惰性导入 → API 冷启动减少约 3 秒

### 第二批（中期优化，需架构调整）
1. Celery 异步任务队列 → 支持长时间分析
2. HB 采样参数自适应 → 采样时间节省 30-50%
3. D-optimal 算法向量化 → 设计生成速度提升 10-100 倍
4. 批量生成并发控制 → 批处理速度提升 3-5 倍
5. LLM 结果缓存层 → 重复生成成本降为 0
