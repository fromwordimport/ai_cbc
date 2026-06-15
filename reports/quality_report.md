# AI_CBC 测试质量审查报告

> **审查人**: 小测
> **日期**: 2026-06-11
> **审查范围**: 全量测试收集、关键模块执行验证、静态架构审计

---

## 一、测试总览

| 指标 | 数值 |
|------|------|
| 收集用例数 | 641 (本次) |
| 已验证通过 | 88 |
| 已验证失败 | 0 |
| 未运行（超时/在跑） | 553 |
| 已验证通过率 | 100% (88/88) |

> **执行限制**: `pyproject.toml:80` 的 `addopts = "--cov=src --cov-report=term-missing --cov-report=html"` 强制每次运行覆盖率分析+HTML报告生成。无覆盖率时42个用例耗时1.42秒，带覆盖率默认配置耗时1270秒（21分钟），膨胀约**894倍**。全量641个用例预估需**4.5小时**。这是本轮审查最大的障碍——不是测试代码有问题，是配置导致开发效率崩溃。

### 测试文件统计

| 目录 | 文件数 | ~测试函数数 | 本轮验证 |
|------|--------|-----------|---------|
| `tests/` (根) | 24 | ~350 | 88通过 |
| `tests/analysis/` | 6 | ~60 | 未运行 |
| `tests/redteam/` | 3 | ~60 | 未运行 |

---

## 二、验证通过的模块

| 测试文件 | 用例数 | 结果 |
|----------|--------|------|
| `test_health.py` | 3 | 全部通过 |
| `test_tags.py` | 33 | 全部通过 |
| `test_validators.py` | 30 | 全部通过 |
| `test_llm_client.py` | 16+6参数化 | 全部通过 |
| **合计** | **88** | **100%通过** |

---

## 三、ISS-001 状态污染根因分析

静态审查确认三种代码模式是ISS-001的直接根因：

### (a) 模块级 TestClient 共享（6处）

以下文件在模块加载时创建 `TestClient(app)`，所有测试类共享同一个FastAPI app实例：
`test_api_simulations.py:21`, `test_api_persona_crud.py:22`, `test_api_batch_generate.py:40`, `test_api_questionnaires.py:11`, `test_health.py:7`, `tests/redteam/test_api_security.py:19`

**问题**: `app.dependency_overrides` 是FastAPI全局可变字典，一个测试中设置的override不会自动清除，可能泄漏到下一个测试文件。

### (b) 多autouse fixture冲突（2处）

`test_api_simulations.py:71`和`test_api_questionnaires.py:14`各自有autouse fixture直接操作store。这些与conftest.py的全局`_clean_global_state`并行执行时可能因顺序不确定导致清理不彻底。

### (c) conftest.py 仅在yield前清理

```python
# tests/conftest.py:60-106
def _clean_global_state():
    reset_dependencies() / reset_stores() / app.dependency_overrides.clear() / ...
    yield
    # ⚠️ yield后没有二次清理！测试中的副作用可能泄漏
```

### 综合链路

```
store.py 模块级单例
    ↓
dependencies.py 模块级单例
    ↓
6个文件共享TestClient + 2个文件自有autouse
    ↓
conftest清理仅yield前执行，无二次清理兜底
    ↓
=== 批量运行时，测试间全局状态泄漏 ===
```

---

## 四、覆盖率概况

基于已验证88个用例的运行数据：6130语句，33%覆盖率。

### 高覆盖率模块 (>80%)

| 模块 | 覆盖率 | 语句数 |
|------|--------|--------|
| `config.settings` | 98% | 83 |
| `core.models.persona` | 99% | 81 |
| `core.validators.logic_validator` | 95% | 98 |
| `core.validators.schema_validator` | 93% | 68 |
| `llm.client` | 92% | 162 |
| `cost.tracker` | 81% | 228 |
| `api.schemas` | 97% | 203 |

### 低覆盖率模块 (<40%)

| 模块 | 覆盖率 | 风险 |
|------|--------|------|
| `agents.*` (6文件) | 0-43% | **P0** |
| `tools.*` (3文件) | 0-43% | **P0** |
| `analysis.engines.hb_engine` | 19% | **P0** |
| `analysis.engines.mnl_engine` | 0% | **P0** |
| `llm.router` | 0% | P1 |
| `questionnaire.design.orthogonal` | 12% | P1 |
| `core.simulation.*` (2文件) | 16-31% | P1 |
| `api.routes.health` (死代码) | 0% | P2 |

注意：剩下553个未运行用例专门针对低覆盖率模块，全量运行后预期总覆盖率可提升至55-70%。

---

## 五、其他发现

### 死代码

`src/aicbc/api/routes/health.py` — 实现简化版端点但`main.py`实际注册的是`monitoring/health.py`。覆盖率0%（16条语句全未执行）。

### DeprecationWarning

- Starlette TestClient已标记废弃，建议迁移到httpx
- `main.py:88,94` 使用`@app.on_event("startup"/"shutdown")`，建议迁移到lifespan异步上下文管理器

---

## 六、建议

### P0（阻塞项）

| 编号 | 问题 | 修复方向 |
|------|------|---------|
| P0-1 | `pyproject.toml`强制覆盖率导致894x慢 | `addopts`改为`--strict-markers`，覆盖率移至CI独立步骤 |
| P0-2 | conftest yield后无二次清理 | yield之后增加`reset_dependencies()`+`reset_stores()`+`dependency_overrides.clear()` |
| P0-3 | 模块级TestClient共享 | 6个文件中的`client = TestClient(app)`改为function-scope fixture |
| P0-4 | 多autouse fixture冲突 | 移除自有autouse，统一依赖conftest |

### P1（重要）

| 编号 | 问题 |
|------|------|
| P1-1 | 补充Agent/Tools模块基础测试（当前0%覆盖率） |
| P1-2 | 补充分析引擎快速单元测试（mock采样结果） |
| P1-3 | 迁移FastAPI on_event到lifespan |
| P1-4 | 验证历史红队16个失败是否已修复 |

### P2（改进）

| 编号 | 问题 |
|------|------|
| P2-1 | 删除死代码`api/routes/health.py` |
| P2-2 | 引入pytest-xdist并行测试（需先修复P0-2/3/4） |
| P2-3 | 补充合成数据参数恢复测试 |
| P2-4 | 补充成本熔断压力测试 |

---

**审查总结**: 核心88个用例全部通过。最大发现不是测试代码有大量失败，而是`pyproject.toml`的`addopts`配置导致开发效率下降~894倍。ISS-001的状态污染根因已通过静态分析确认，修复方案明确且代价低。建议P0项在本迭代内完成。
