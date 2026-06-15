# 实验设计模块重构方案

> **版本**：v1.0  
> **维护者**：小联（领域专家）  
> **关联审查**：`reports/methodology_review.md`  
> **日期**：2026-06-12

---

## 1. P0-1：正交设计 vs 平衡设计的命名与实现纠正

### 1.1 问题确认

`orthogonal.py` 的 `_select_balanced_subset` 贪心算法只优化**每列（单属性）**的边际水平频率平衡——即每个 `attribute_id` 下各 `level_value` 出现次数尽量接近 `target_size / n_levels`。算法完全不考察**任意两列的二维联合频率**。因此它产生的是 **平衡设计 (Balanced Design)**，而非 **正交设计 (Orthogonal Design)**。

正交设计的定义：对任意两个属性 `(attr_a, attr_b)`，其水平组合 `(level_i, level_j)` 在设计中出现的次数均相等（或尽量相等）。这是二维联合正交性要求，当前实现完全不满足。

### 1.2 影响范围

| 文件 | 影响 |
|------|------|
| `src/aicbc/questionnaire/design/orthogonal.py` | 核心修改 |
| `src/aicbc/questionnaire/generator.py` | 调用方需适配新类名/入口 |
| `src/aicbc/questionnaire/models.py` | `DesignAlgorithm.ORTHOGONAL` 枚举，可保留也可新增 |
| `tests/test_orthogonal_design.py` | 需重写/扩展 |
| `docs/数据字典.md`、`docs/端到端数据流与集成规范.md` | 文档同步 |

### 1.3 方案A（推荐）：重命名 + 新增真正正交设计类

**操作**：
1. 将 `orthogonal.py` 重命名为 `balanced.py`。
2. 将 `generate_orthogonal_questionnaire` 重命名为 `generate_balanced_questionnaire`。
3. 在 `DesignAlgorithm` 枚举中新增 `BALANCED = "balanced"`（保留 `ORTHOGONAL`）。
4. 新建 `orthogonal.py`，实现真正的正交设计：
   - 使用 **Latin Square**（2属性场合）或 **Orthogonal Array (OA)** 构建。
   - 对于混合水平（如 4 水平 × 3 水平），采用 **Full Factorial → 贪心行选择（目标函数 = 二维联合频率偏差）**。
   - 核心指标：`_check_orthogonality` 要改为计算二维联合平衡度，而非仅一维边际平衡。
5. `generator.py` 中路由逻辑更新，支持三种算法路线。

**利**：
- 概念正确，用户/下游不会误用。
- 保留了 `BalancedDesign` 作为轻量基线（对于小设计、无法构造 OA 的场合仍有价值）。
- 与领域标准术语一致。

**弊**：
- 改动量较大（涉及 6+ 文件）。
- 需要实现 OA 构造逻辑或引入 `pyDOE2` / `OApackage` 依赖（或手写小型 OA 查找表）。
- 旧测试需迁移/重写。

### 1.4 方案B：增强 `_select_balanced_subset` 增加二维约束

**操作**：
1. 保留 `orthogonal.py` 文件名和函数名不变。
2. 修改 `_select_balanced_subset` 的评分函数：从 `max_dev = max(一维边际偏差)` 改为 `max_dev = max(一维边际偏差) + λ * max(二维联合偏差)`。
3. 新增辅助函数 `_joint_freq_deviation(selected, attrs)` 计算所有属性对的二维联合频率偏差。
4. 更新 `_check_orthogonality` 同样加入二维联合平衡度计算。

**利**：
- 改动量小（仅 `orthogonal.py` 一个文件）。
- 不引入新依赖。
- 向后兼容，现有API不变。

**弊**：
- **不是真正的正交设计**——贪心+惩罚项只是"近似二维平衡"，不保证正交性（OA的数学性质无法通过贪心模拟）。
- λ 权重需要调参，无理论最优值。
- 对于 5+ 属性场合，贪心搜索的联合偏差空间爆炸（C(n,2) 个属性对 × 各对的水平组合），性能下降。
- 名实不符：函数仍叫 `_select_balanced_subset`，本质上仍是平衡设计。

### 1.5 推荐决策

**推荐方案A**。理由：
- P0 级别的模型方法论错误，打补丁（方案B）无法根本解决——贪心无法保证正交性。
- `BalancedDesign` 作为独立概念有存在价值（快速、无依赖、适合小设计），不应混用名称。
- 方案A为后续扩展（如 Bayesian D-optimal、Partial Profile）留出清晰的架构空间。

---

## 2. P0-2：ProhibitedPair 跨属性约束重构

### 2.1 当前模型

```python
class ProhibitedPair(BaseModel):
    attribute_id: str          # 单一属性ID
    level_value: Any           # 该属性下禁止的水平值
```

`_is_prohibited` 逻辑：

```python
def _is_prohibited(profile, prohibited_pairs):
    return any(profile.get(pair.attribute_id) == pair.level_value 
               for pair in prohibited_pairs)
```

**缺陷**：每个 `ProhibitedPair` 只能表达对单个属性某个水平的禁止。无法表达"西门子 AND ¥2999"这种跨属性组合约束。即无法禁止特定属性组合。

### 2.2 目标模型

```python
class ProhibitedPair(BaseModel):
    """禁止的属性水平组合 —— 支持跨属性联合约束。
    
    每个 ProhibitedPair 是一个 or-of-ands：
    pairs 列表中的所有条件必须同时满足才触发禁止。
    多个 ProhibitedPair 之间是 OR 关系（任一命中即禁止）。
    """
    pairs: list[Condition] = Field(
        ..., 
        min_length=1, 
        description="AND-connected conditions; all must match to trigger prohibition"
    )

class Condition(BaseModel):
    attribute_id: str
    level_value: Any
```

**语义**：
- `ProhibitedPair(pairs=[Condition("brand", "西门子"), Condition("price", 2999)])` → 禁止 brand=西门子 AND price=2999。
- 单属性禁止：`ProhibitedPair(pairs=[Condition("brand", "美的")])` → 等价于旧模型。
- 多个 `ProhibitedPair`：任一命中即禁止（旧逻辑维持）。

**向后兼容处理**：提供迁移函数或 Pydantic `model_validator` 自动将旧格式 `{"attribute_id": "x", "level_value": "y"}` 转换为新格式。

### 2.3 改动点详解

#### 2.3.1 `src/aicbc/questionnaire/models.py`

```python
# 新增 Condition 模型
class Condition(BaseModel):
    attribute_id: str
    level_value: Any

# 改 ProhibitedPair
class ProhibitedPair(BaseModel):
    pairs: list[Condition] = Field(..., min_length=1)
    
    # 兼容旧格式的validator（可选）
    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_format(cls, data):
        if isinstance(data, dict) and "attribute_id" in data:
            # 旧格式 -> 新格式
            return {"pairs": [{"attribute_id": data["attribute_id"], 
                               "level_value": data["level_value"]}]}
        return data
```

#### 2.3.2 `src/aicbc/questionnaire/design/d_optimal.py` 的 `_is_prohibited`

```python
# 旧（单属性）：
def _is_prohibited(profile, prohibited_pairs):
    return any(
        profile.get(pair.attribute_id) == pair.level_value 
        for pair in prohibited_pairs
    )

# 新（跨属性联合）：
def _is_prohibited(profile: dict[str, Any], 
                   prohibited_pairs: list[ProhibitedPair]) -> bool:
    for pair in prohibited_pairs:
        # 所有 conditions 必须同时满足
        if all(
            profile.get(cond.attribute_id) == cond.level_value
            for cond in pair.pairs
        ):
            return True
    return False
```

`generate_candidate_set()` 无需改动（它只调用 `_is_prohibited`，接口不变）。

#### 2.3.3 Fedorov 交换算法 (`d_optimal_design`)

**不需要改动**。候选集在生成时已经过滤掉了 `ProhibitedPair` 违规 profile。交换算法只在候选集内交换，不会引入被过滤的 profile。`_has_duplicates_in_set` 也不受影响。

#### 2.3.4 `src/aicbc/questionnaire/validators.py` 的 `validate_prohibited_pairs`

```python
# 旧（单属性检查）：
for pair in prohibited_pairs:
    if alt.attributes.get(pair.attribute_id) == pair.level_value:
        violations.append(...)

# 新（跨属性联合检查）：
for pair in prohibited_pairs:
    if all(
        alt.attributes.get(cond.attribute_id) == cond.level_value
        for cond in pair.pairs
    ):
        violations.append(
            f"选择集 {cs.choice_set_id} 选项 {alt.alt_index}: "
            f"违反禁止组合 {[(c.attribute_id, c.level_value) for c in pair.pairs]}"
        )
```

#### 2.3.5 影响文件汇总

| 文件 | 改动类型 | 工作要点 |
|------|---------|---------|
| `src/aicbc/questionnaire/models.py` | 新增 + 修改 | 新增 `Condition`，改 `ProhibitedPair`，加向后兼容 validator |
| `src/aicbc/questionnaire/design/d_optimal.py` | 修改 | 改 `_is_prohibited` 逻辑 |
| `src/aicbc/questionnaire/validators.py` | 修改 | 改 `validate_prohibited_pairs` 逻辑 |
| `tests/test_d_optimal.py` | 修改 + 新增 | 新增跨属性禁止测试用例 |
| `tests/test_questionnaire_validator.py` | 修改 | 适配新格式 |
| `docs/数据字典.md` | 修改 | 更新 `prohibited_pairs` 示例 |

### 2.4 边界情况注意

- **空 `prohibited_pairs`**：`_is_prohibited` 的 `any()` 返回 `False`，不受影响。
- **单属性禁止**：`pairs` 长度为 1，`all()` 退化为单条件检查，与旧行为一致。
- **候选集过小**：如果禁止组合太多导致候选集小于所需 profile 数，`d_optimal_design` 已有的 `ValueError("no legal profiles...")` 会触发。但需考虑 improvement：给出更明确的错误信息（哪些禁止组合导致了候选集不足）。

---

## 3. 工作量估算

| 任务 | 估时(h) | 说明 |
|------|--------|------|
| **P0-1 方案A** | | |
| 重命名 `orthogonal.py` → `balanced.py` | 0.5 | 纯重命名 + 更新 imports |
| `DesignAlgorithm` 新增 `BALANCED` | 0.5 | 枚举 + generator 路由 |
| 实现正交设计核心算法 | 4.0 | OA 查找表 / Latin Square / Full Factorial 贪心 |
| `_check_orthogonality` 改二维联合 | 1.0 | 新评分函数 |
| 测试迁移与新增 | 2.0 | 旧测试适配 `balanced`，新测试覆盖 OA |
| 文档同步 | 0.5 | 数据字典、集成规范 |
| **P0-1 小计** | **8.5h** | |
| | | |
| **P0-2 ProhibitedPair重构** | | |
| `Condition` 模型定义 | 0.5 | models.py |
| `ProhibitedPair` 重构 + 向后兼容 | 0.5 | models.py |
| `_is_prohibited` 改动 | 0.5 | d_optimal.py |
| `validate_prohibited_pairs` 改动 | 0.5 | validators.py |
| 测试更新 | 1.5 | 新增跨属性测试，适配旧测试 |
| 文档同步 | 0.5 | 数据字典示例 |
| **P0-2 小计** | **4.0h** | |
| | | |
| **合计** | **12.5h** | 约 2 个工作日（含 review） |

---

## 4. 实施建议

1. **先做 P0-2**（依赖少，改动集中，4h 可完成），再攻克 P0-1（架构级变更）。
2. P0-1 过程中，`BalancedDesign` 作为中间产物可以先合并，降低单次 PR 复杂度。
3. 正交设计核心算法涉及 OA 查找表建议：不引入 `pyDOE2`（依赖太重），改为手写固定 OA 表（`L4`, `L8`, `L9`, `L12`, `L16`, `L18`, `L27` 已覆盖常见设计规模），超出范围的 fallback 到 `BalancedDesign` 并 emit warning。
4. `ProhibitedPair` 的向后兼容 validator 建议保留 2 个版本后删除（标注 `@deprecated`）。
