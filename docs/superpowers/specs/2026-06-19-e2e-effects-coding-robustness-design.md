# AI_CBC E2E Effects Coding 列名断言健壮化设计

> **版本**：v1.0
> **日期**：2026-06-19
> **负责人**：小测（QA Engineer）
> **相关角色**：小数（Data/Modeling Scientist）、小端（Backend Engineer）
> **状态**：待实施

## 1. 背景与目标

### 1.1 背景

运行

```bash
uv run pytest -x --timeout=60
```

时，`tests/e2e/test_full_pipeline.py::TestFullPipelineE2E::test_full_pipeline_study_to_analysis` 失败：

```
AssertionError: assert 'features_0' in ['price', 'brand_0', 'brand_1', 'brand_2',
                                        'capacity_0', 'capacity_1', ...]
```

### 1.2 根因

当前 `QuestionnaireGenerator._dishwasher_default_attributes()` 返回的默认洗碗机属性为：

- `price`（4 水平，PRICE 类型 → 1 参数）
- `brand`（4 水平 → 3 参数）
- `capacity`（4 水平 → 3 参数）
- `energy`（3 水平 → 2 参数）
- `spray_arm`（3 水平 → 2 参数）
- `installation`（4 水平 → 3 参数）
- `drying`（4 水平 → 3 参数）

共计 **17 个 effects coding 列**。

但 `test_full_pipeline_study_to_analysis` 仍按旧属性集合硬编码断言：

- 期望存在 `features_0`、`features_1`（当前默认属性中已无 `features`）
- 期望总列数为 12

同文件中的 `TestEffectsCodingConsistency::test_naming_convention_matches_datadict` 也硬编码了 17 个列名。虽然它恰好与数据字典 Section 10.1 的示例一致，但示例属性（含 `features`）已与当前代码默认属性不一致。

### 1.3 目标

1. 修复当前 E2E 测试失败。
2. 将两个测试从“硬编码列名清单”改造为“检查编码规则的结构不变量”。
3. 使默认洗碗机属性再调整时，这两个测试不再误报。
4. 不改动生产代码和默认属性定义。

## 2. 设计原则

- **测规则不测清单**：E2E 测试应验证 effects coding 命名约定、列数与 `n_parameters` 一致、分析输出与 `feature_cols` 对齐，而不是假设某个固定属性集合。
- **单一职责**：`test_naming_convention_matches_datadict` 只验证命名约定；属性清单的正确性由 `test_study_creation_produces_valid_study` 等测试承担。
- **最小改动**：仅修改两个测试方法，不动生产代码、不动数据字典。

## 3. 改造范围

| 文件 | 方法 | 动作 |
|---|---|---|
| `tests/e2e/test_full_pipeline.py` | `TestFullPipelineE2E::test_full_pipeline_study_to_analysis` | 移除硬编码列名断言，改为结构不变量断言 |
| `tests/e2e/test_full_pipeline.py` | `TestEffectsCodingConsistency::test_naming_convention_matches_datadict` | 移除硬编码 17 列集合，改为命名规则与索引范围断言 |

不改动：

- `src/aicbc/questionnaire/design/effects_coding.py`
- `src/aicbc/analysis/preprocessing.py`
- `src/aicbc/questionnaire/generator.py`
- `docs/数据字典.md`

## 4. `test_full_pipeline_study_to_analysis` 改造细节

### 4.1 当前问题代码

```python
# Effects coding column naming: {attr_id}_{level_index}
feature_cols = get_feature_columns(attributes)
expected_param_count = n_parameters(attributes)
assert len(feature_cols) == expected_param_count
# price should be a single column (continuous)
assert "price" in feature_cols
# 3-level categoricals → 2 parameters each (brand has 4 levels → 3)
assert "capacity_0" in feature_cols
assert "capacity_1" in feature_cols
assert "installation_0" in feature_cols
assert "installation_1" in feature_cols
assert "features_0" in feature_cols
assert "features_1" in feature_cols
assert "brand_0" in feature_cols
assert "brand_1" in feature_cols
assert "brand_2" in feature_cols
assert "energy_0" in feature_cols
assert "energy_1" in feature_cols
# Total: 1 (price) + 2 + 2 + 2 + 3 + 2 = 12
assert len(feature_cols) == 12
```

### 4.2 改造后代码

```python
# Effects coding column naming: {attr_id}_{level_index}
feature_cols = get_feature_columns(attributes)
expected_param_count = n_parameters(attributes)
assert len(feature_cols) == expected_param_count

# price 作为价格属性，应为单列
assert "price" in feature_cols

# 对每个分类/序数属性，验证其产生 k-1 个列，且索引为 0..k-2
for attr in attributes:
    if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
        prefix_cols = [c for c in feature_cols if c.startswith(f"{attr.id}_")]
        assert len(prefix_cols) == len(attr.levels) - 1, (
            f"Attribute {attr.id} should have {len(attr.levels) - 1} columns, "
            f"got {len(prefix_cols)}"
        )
        expected_names = [f"{attr.id}_{i}" for i in range(len(attr.levels) - 1)]
        assert set(prefix_cols) == set(expected_names), (
            f"Attribute {attr.id} columns mismatch: expected {expected_names}, "
            f"got {prefix_cols}"
        )
    else:
        assert attr.id in feature_cols, f"Continuous/price attribute {attr.id} missing"
```

### 4.3 保持不变的部分

- `validate_dataset` 断言
- `HBEngine.fit(df_long, feature_cols)` 及后续收敛、个体效用断言
- WTP / 重要性 / 市场份额模拟断言

这些部分已经使用 `feature_cols` 变量，天然与属性集合解耦。

## 5. `test_naming_convention_matches_datadict` 改造细节

### 5.1 当前问题代码

```python
expected = {
    "price",
    "capacity_0", "capacity_1", "capacity_2",
    "installation_0", "installation_1", "installation_2",
    "spray_arm_0", "spray_arm_1",
    "brand_0", "brand_1", "brand_2",
    "energy_0", "energy_1",
    "drying_0", "drying_1", "drying_2",
}
actual = set(feature_cols)
assert actual == expected
```

该断言假设默认洗碗机属性集合固定不变，且与数据字典 Section 10.1 示例完全一致。

### 5.2 改造后代码

```python
feature_cols = get_feature_columns(dishwasher_study.attributes)

# 总列数必须等于参数总数
assert len(feature_cols) == n_parameters(dishwasher_study.attributes)

attr_ids = {attr.id for attr in dishwasher_study.attributes}

# 验证每个列名都符合 {attribute_id}_{level_index} 或 {attribute_id} 的约定
for col in feature_cols:
    if "_" in col:
        attr_id, idx_str = col.rsplit("_", 1)
        assert attr_id in attr_ids, f"Column {col} references unknown attribute {attr_id}"
        assert idx_str.isdigit(), f"Column {col} has non-numeric level index {idx_str}"
    else:
        assert col in attr_ids, f"Column {col} does not match any attribute id"

# 对每个分类/序数属性，验证索引范围 0..k-2 且恰好 k-1 列
for attr in dishwasher_study.attributes:
    if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
        expected = {f"{attr.id}_{i}" for i in range(len(attr.levels) - 1)}
        actual = {c for c in feature_cols if c.startswith(f"{attr.id}_")}
        assert actual == expected, (
            f"Attribute {attr.id} expected columns {sorted(expected)}, got {sorted(actual)}"
        )
```

### 5.3 与数据字典的关系

改造后，该测试验证的是数据字典中定义的**命名规则**（`{attribute_id}_{level_index}`，索引范围 `0` 到 `n_levels - 2`），而非某一份固定的属性示例清单。

数据字典 Section 10.1 的洗碗机示例当前使用旧属性 `features`，与代码默认属性不一致。本次设计**不更新数据字典**，因为：

- 命名规则本身仍然正确且有效。
- 示例更新属于独立的文档同步任务，不应与测试健壮化混在同一个变更中。
- 改造后的测试不再依赖示例列名，因此不会因示例过旧而失败。

如果后续需要同步数据字典示例，应另提文档更新任务。

## 6. 测试验证计划

| 命令 | 目的 |
|---|---|
| `uv run pytest tests/e2e/test_full_pipeline.py::TestFullPipelineE2E::test_full_pipeline_study_to_analysis -v --timeout=60` | 验证原失败点通过 |
| `uv run pytest tests/e2e/test_full_pipeline.py::TestEffectsCodingConsistency::test_naming_convention_matches_datadict -v --timeout=60` | 验证命名约定测试通过 |
| `uv run pytest tests/e2e/test_full_pipeline.py::TestEffectsCodingConsistency -v --timeout=60` | 验证 effects coding 相关测试无回归 |
| `uv run pytest tests/e2e/test_full_pipeline.py -v --timeout=300` | 验证整个 E2E 文件无回归 |
| `uv run ruff check tests/e2e/test_full_pipeline.py` | 代码风格检查 |

## 7. 风险与权衡

| 风险/权衡 | 说明 | 缓解 |
|---|---|---|
| 测试不再捕获“默认属性集合与数据字典示例不一致” | 改造后测试只验证规则，不验证具体清单 | 该职责由 `test_study_creation_produces_valid_study` 的 `attr_ids` 断言承担；数据字典示例另任务同步 |
| 改动测试文件需授权 | 根目录 `CLAUDE.md` 要求修改测试文件前必须获得用户明确授权 | 本设计已获得用户确认，实施前再次在实现计划中明确 |
| 结构断言可能比原断言弱 | 原断言能发现属性被意外替换为完全不相关名称；新断言仍能发现列名格式错误和数量错误 | 保留 `test_study_creation_produces_valid_study` 对具体属性 id 的检查 |
| 其他测试可能仍硬编码旧列名 | 本次只改造明确提到的两个测试 | 实施前用 `grep` 检查仓库中是否还有 `features_0` 等硬编码引用 |

## 8. 实施前置检查

在按本设计实施前，应确认：

1. 仓库中除这两个测试外，没有其他硬编码依赖 `features_0` / `features_1` 的测试或生产代码。
2. 用户已明确授权修改 `tests/e2e/test_full_pipeline.py`。
3. 实施计划通过 `writing-plans` 技能进一步细化。

## 9. 相关文档

- [`tests/e2e/test_full_pipeline.py`](../../../tests/e2e/test_full_pipeline.py)
- [`src/aicbc/questionnaire/design/effects_coding.py`](../../../src/aicbc/questionnaire/design/effects_coding.py)
- [`src/aicbc/analysis/preprocessing.py`](../../../src/aicbc/analysis/preprocessing.py)
- [`docs/数据字典.md`](../../../docs/数据字典.md)
- [`tests/CLAUDE.md`](../../../tests/CLAUDE.md)
- [`CLAUDE.md`](../../../CLAUDE.md)
