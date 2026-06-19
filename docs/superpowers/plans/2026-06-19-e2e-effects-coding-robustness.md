# E2E Effects Coding 列名断言健壮化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `tests/e2e/test_full_pipeline.py` 中两个硬编码 effects coding 列名的测试改造为检查结构不变量，修复当前 E2E 失败并解除对洗碗机默认属性清单的耦合。

**Architecture:** 不改动生产代码与默认属性定义，仅在两个测试方法内部用 `get_feature_columns(attributes)`、`n_parameters(attributes)` 和属性元数据推导出期望列名，验证 `{attribute_id}_{level_index}` 规则及索引范围。

**Tech Stack:** Python, pytest, Pydantic models (`Attribute`, `AttributeType`), project-local utilities (`get_feature_columns`, `n_parameters`, `to_long_format`).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `tests/e2e/test_full_pipeline.py` | Modify | 包含两个需要改造的测试方法 |
| `docs/superpowers/specs/2026-06-19-e2e-effects-coding-robustness-design.md` | Read-only reference | 已批准的设计文档 |

---

### Task 1: Verify the current failure

**Files:**
- Read: `tests/e2e/test_full_pipeline.py:409-449`

- [ ] **Step 1: Run the failing test**

```bash
uv run pytest tests/e2e/test_full_pipeline.py::TestFullPipelineE2E::test_full_pipeline_study_to_analysis -v --timeout=60
```

- [ ] **Step 2: Confirm the failure matches the spec**

Expected output contains:

```
AssertionError: assert 'features_0' in ['price', 'brand_0', 'brand_1', 'brand_2', ...]
```

- [ ] **Step 3: Check for other hard-coded `features_*` references**

```bash
grep -Rn "features_0\|features_1" tests/ src/
```

Expected: only `tests/e2e/test_full_pipeline.py` contains these strings in code. Documentation files may reference them but are out of scope.

---

### Task 2: Refactor `test_full_pipeline_study_to_analysis`

**Files:**
- Modify: `tests/e2e/test_full_pipeline.py:430-449`

- [ ] **Step 1: Locate the hard-coded assertions**

Read lines 430–449 in `tests/e2e/test_full_pipeline.py`. The block starts after:

```python
# Effects coding column naming: {attr_id}_{level_index}
feature_cols = get_feature_columns(attributes)
expected_param_count = n_parameters(attributes)
assert len(feature_cols) == expected_param_count
```

and ends before:

```python
# ── Step 4b: Validate dataset ──
```

- [ ] **Step 2: Replace with structural assertions**

Replace the entire hard-coded block (lines 430–449) with:

```python
        # Effects coding column naming: {attr_id}_{level_index}
        feature_cols = get_feature_columns(attributes)
        expected_param_count = n_parameters(attributes)
        assert len(feature_cols) == expected_param_count

        # price should be a single column (continuous/price attribute)
        assert "price" in feature_cols

        # Each categorical/ordinal attribute produces k-1 columns with indices 0..k-2
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
                assert attr.id in feature_cols, (
                    f"Continuous/price attribute {attr.id} missing from feature_cols"
                )
```

Note: `AttributeType` is already imported at the top of the file (line 62) and `n_parameters` is imported at line 59.

- [ ] **Step 3: Run the refactored test**

```bash
uv run pytest tests/e2e/test_full_pipeline.py::TestFullPipelineE2E::test_full_pipeline_study_to_analysis -v --timeout=60
```

Expected: PASS.

- [ ] **Step 4: Commit the change**

```bash
git add tests/e2e/test_full_pipeline.py
git commit -m "test(e2e): make feature_cols assertions robust to attribute changes

Replace hard-coded feature column list in test_full_pipeline_study_to_analysis
with structural checks derived from study attributes."
```

---

### Task 3: Refactor `test_naming_convention_matches_datadict`

**Files:**
- Modify: `tests/e2e/test_full_pipeline.py:844-873`

- [ ] **Step 1: Locate the hard-coded expected set**

Read lines 844–873 in `tests/e2e/test_full_pipeline.py`. The method is:

```python
def test_naming_convention_matches_datadict(self, dishwasher_study: CBCStudy):
```

- [ ] **Step 2: Replace with naming-rule assertions**

Replace the entire method body with:

```python
    def test_naming_convention_matches_datadict(self, dishwasher_study: CBCStudy):
        """Column names follow {attribute_id}_{level_index} convention."""
        feature_cols = get_feature_columns(dishwasher_study.attributes)

        # Total parameter count matches the design
        assert len(feature_cols) == n_parameters(dishwasher_study.attributes)

        attr_ids = {attr.id for attr in dishwasher_study.attributes}

        # Every column matches either {attribute_id} or {attribute_id}_{level_index}
        for col in feature_cols:
            if "_" in col:
                attr_id, idx_str = col.rsplit("_", 1)
                assert attr_id in attr_ids, (
                    f"Column {col} references unknown attribute {attr_id}"
                )
                assert idx_str.isdigit(), (
                    f"Column {col} has non-numeric level index {idx_str}"
                )
            else:
                assert col in attr_ids, (
                    f"Column {col} does not match any attribute id"
                )

        # Each categorical/ordinal attribute has exactly k-1 columns indexed 0..k-2
        for attr in dishwasher_study.attributes:
            if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
                expected = {f"{attr.id}_{i}" for i in range(len(attr.levels) - 1)}
                actual = {c for c in feature_cols if c.startswith(f"{attr.id}_")}
                assert actual == expected, (
                    f"Attribute {attr.id} expected columns {sorted(expected)}, "
                    f"got {sorted(actual)}"
                )
```

- [ ] **Step 3: Run the refactored test**

```bash
uv run pytest tests/e2e/test_full_pipeline.py::TestEffectsCodingConsistency::test_naming_convention_matches_datadict -v --timeout=60
```

Expected: PASS.

- [ ] **Step 4: Commit the change**

```bash
git add tests/e2e/test_full_pipeline.py
git commit -m "test(e2e): make naming convention test robust to attribute changes

Replace hard-coded 17-column expected set in test_naming_convention_matches_datadict
with structural checks for the {attribute_id}_{level_index} rule."
```

---

### Task 4: Run the full E2E file

**Files:**
- Read-only: `tests/e2e/test_full_pipeline.py`

- [ ] **Step 1: Run all tests in the file**

```bash
uv run pytest tests/e2e/test_full_pipeline.py -v --timeout=300
```

- [ ] **Step 2: Confirm no regressions**

Expected: all tests pass. Note that tests marked `@pytest.mark.slow` will execute and may take longer; the `--timeout=300` flag allows up to 5 minutes per test.

---

### Task 5: Run lint and format checks

**Files:**
- Read-only: `tests/e2e/test_full_pipeline.py`

- [ ] **Step 1: Run ruff lint**

```bash
uv run ruff check tests/e2e/test_full_pipeline.py
```

Expected: no errors.

- [ ] **Step 2: Run ruff format check**

```bash
uv run ruff format --check tests/e2e/test_full_pipeline.py
```

Expected: no formatting differences. If there are differences, run `uv run ruff format tests/e2e/test_full_pipeline.py` and commit.

- [ ] **Step 3: Commit any format fixes**

```bash
git add tests/e2e/test_full_pipeline.py
git commit -m "style(tests): ruff format test_full_pipeline.py"
```

---

## Self-Review Checklist

- [ ] **Spec coverage:** Both spec requirements (refactor `test_full_pipeline_study_to_analysis` and `test_naming_convention_matches_datadict`) are covered by Task 2 and Task 3.
- [ ] **No placeholders:** No TBD/TODO/"implement later" remains.
- [ ] **Type consistency:** Uses `AttributeType` and `n_parameters` consistently with existing imports.
- [ ] **Test commands:** All commands include exact paths and expected outcomes.
- [ ] **Commit guidance:** Each task includes a commit suggestion following conventional commits.
- [ ] **Scope:** Only `tests/e2e/test_full_pipeline.py` is modified; no production code changes.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-19-e2e-effects-coding-robustness.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

**Which approach?**
