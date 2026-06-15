# AI_CBC 方法论审查报告

> **审查人**: 小联（联合分析领域专家）
> **日期**: 2026-06-11
> **依据**: CLAUDE.md方法论要求、数据字典v1.0、洗碗机CBC实验设计方案v1.0

---

## 一、实验设计审查

### 1.1 正交设计算法 (`orthogonal.py`)

**P0 关键发现**: 该算法实现的是**平衡设计(balanced design)**，而非**正交设计(orthogonal design)**。真正的正交设计需保证任意两个属性之间各水平组合以相等频率出现（正交数组OA或Latin square构造）。当前算法仅保证单属性边际平衡，缺少二维联合正交性保证。

| 方法 | 功能 | 评估 |
|------|------|------|
| `_generate_full_factorial()` | itertools.product枚举全部组合 | 正确 |
| `_select_balanced_subset()` | 贪心选择最小化水平频率偏差 | **仅边际平衡，非正交** |
| `_distribute_to_choice_sets()` | 随机打乱后按序分配 | **缺集内去重检查(P1)** |
| `_check_orthogonality()` | 仅检验一维频率平衡 | **名不副实(P2)** |

### 1.2 Effects Coding实现 (`effects_coding.py`)

| 检查项 | 判定 |
|--------|------|
| k水平 → k-1参数: one-hot + 负和末水平 | 正确 |
| 末水平恢复: `-(前k-1之和)` | 正确 |
| 价格标准化: z-score `(v-μ)/σ` | 正确 |
| 命名: `{attr_id}_{level_index}` | 与数据字典一致 |
| 恢复: `_recover_level_utilities()` | 正确 |

验证：3水平capacity编码 `[1,0]`, `[0,1]`, `[-1,-1]`，恢复时三水平效用和为0。正确。

### 1.3 D-optimal设计 (`d_optimal.py`)

**P0 关键Bug**: `ProhibitedPair`模型和`_is_prohibited()`仅支持单属性约束，无法表达"西门子且2999"这样的跨属性禁止组合。设计文档定义的4个禁止组合全部无法生效。

其他: Fedorov交换算法、D值优化、收敛判定均正确实现。

### 1.4 设计文档一致性

| 设计要求 | 实现 | 一致性 |
|---------|------|--------|
| 6属性,12题,3选项 | 支持自定义 | 一致 |
| Effects coding, 12参数 | 代码1+2+2+2+3+2=12 | 一致 |
| D-eff >= 0.80 | 计算正确 | 一致 |
| 位置均衡 | **未实现** | 不一致 |
| 禁止组合 | **模型不支持跨属性** | P0 |

### 1.5 效率计算 (`efficiency.py`)

D-efficiency = det^(1/p)/(trace/p)、A-efficiency = p/trace、条件Logit分块信息矩阵、数值稳定性处理 — 全部正确。

---

## 二、模型解读逻辑

### 2.1 效用值解读

**HB模型**: 混合Logit规格、非中心化参数化、LKJCholeskyCov先验(η=2)、Log-softmax似然、R-hat<1.1收敛判定、ESS>400可靠性判定 — 全部正确，学术规范。

**MNL模型**: statsmodels ConditionalLogit、McFadden R²、AIC/BIC、Null LL计算 — 正确。收敛性仅依靠"fit()未raise"判断，缺乏梯度检验(P2)。

### 2.2 市场模拟 (`market_simulator.py`)

- Logit规则: `P_j = exp(u_ij)/Σexp(u_ik) → share_j = avg(P_j)`，数值稳定 — 正确
- First Choice规则: `choice_i = argmax u_ij` — 正确
- CI: bootstrap percentile (2.5%, 97.5%) — 合理

**P1**: `segment_filter`参数未实际使用（line 85是`pass`），分段模拟功能失效。

### 2.3 WTP计算 (`wtp.py`)

**P1 关键问题: 价格标准化未反标准化**

`effects_coding.py`将价格标准化为z-score: `encoded = (price - μ)/σ`。因此 WTP = -beta_feat/beta_price 结果单位是**标准化价格单位**而非CNY。

洗碗机示例 (μ=4499, σ≈1118):
```
WTP(当前) = 0.4/0.5 = 0.8 标准化单位 → 含义不明
WTP(正确) = 0.8 × 1118 = 894 CNY → 可解读
```

**正确公式**: `WTP_CNY = -(beta_feat / beta_price) × σ_price`

---

## 三、重要性计算 (`importance.py`)

公式: `Importance_attr = Range_attr / ΣRange_all`，Range = max(level_utility) - min(level_utility) — 正确。

- 分类属性: effects coding恢复后range — 正确
- 价格: `|coef| × price_range` — 正确
- 连续: `|coef| × 10.0` — P2: 魔法数字
- 归一化到100% — 正确
- 聚合: 经验分位数法 — 正确且稳健

---

## 四、测试结果

`tests/test_orthogonal_design.py`: **16 passed, 4 warnings**

测试覆盖: orthogonal.py 100%，d_optimal.py仅16%。分析模块（WTP/重要性/市场模拟）零测试覆盖。

---

## 五、问题汇总

### P0 (阻塞发布)

| 编号 | 问题 | 位置 | 修复方向 |
|------|------|------|---------|
| 1 | "正交设计"实为平衡设计，非正交 | `orthogonal.py:39-96` | 重命名或实现真正OA算法 |
| 2 | ProhibitedPair不支持跨属性组合 | `models.py:115-119`, `d_optimal.py:41-45` | 重构为组合约束 `list[tuple[str,Any]]` |

### P1 (发布前修复)

| 编号 | 问题 |
|------|------|
| 3 | WTP未反标准化价格 — 结果无业务意义 |
| 4 | 正交设计无集内去重 |
| 5 | segment_filter未实现 — 分段模拟功能失效 |
| 6 | 位置均衡缺失 |

### P2 (下一迭代)

| 编号 | 问题 |
|------|------|
| 7 | `_check_orthogonality`仅边际检验 |
| 8 | 连续属性魔法数字10 |
| 9 | MNL收敛性未检验 |
| 10 | 分析模块零测试 |
| 11 | 全正价格系数无兜底处理 |

---

## 六、总体评估

| 维度 | 评分 |
|------|------|
| Effects Coding | **优秀** |
| 模型规格 HB/MNL | **优秀** |
| 重要性计算 | 良好 (魔法数字) |
| 市场模拟 | 良好 (segment过滤缺失) |
| WTP计算 | **待修复** (P1: 价格未反标准化，数值无业务意义) |
| 正交设计 | **需重构** (P0: 名不副实) |
| 禁止组合 | **需重构** (P0: 模型不支持跨属性) |
| 测试覆盖 | 不足 (分析模块零测试) |

**结论**: 系统理论基础框架正确——模型规格、编码方案、公式方向均符合联合分析学术标准。但存在2个P0和4个P1问题需在发布前修复。其中WTP的价格单位问题会导致所有支付意愿数值无法进行业务解读。
