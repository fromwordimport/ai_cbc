# AI_CBC 分析引擎验证报告

> **审查人**: 小数
> **日期**: 2026-06-11
> **审查范围**: `src/aicbc/analysis/` 全部源码 + `tests/analysis/` 全部测试

---

## 一、HB引擎审查

### 1.1 模型结构

`src/aicbc/analysis/engines/hb_engine.py`

#### 先验设定

| 参数 | 分布 | 配置值 | 评估 |
|------|------|--------|------|
| mu (人口均值) | Normal(mu0=0, sigma=10) | `mu_prior_mean=0`, `mu_prior_sigma=10` | 弱信息先验，合理。effects coding 下参数范围[-3,3]，sigma=10足够宽松 |
| Sigma (协方差矩阵) | LKJCholeskyCov(eta=2.0) | `lkj_eta=2.0` | eta=2 略倾向于低相关，保守合理 |
| sigma (标准差) | HalfNormal(sigma=2) 或 Exponential(lam=1) | `sigma_prior="half_normal"` | 合理，但有BUG（见下） |
| z (个体偏移) | Normal(0, 1) | 非中心化参数化 | 标准做法，提升NUTS采样效率 |

#### 似然函数

- 使用 **log-softmax** 形式，通过 `pm.Potential("log_likelihood", sum(log_probs))` 加入模型
- `pm.math.log_softmax(utilities)` 内部处理数值稳定性

#### P0-BUG: `build_model` 中 `sigma` 变量为死代码

`hb_engine.py:149-162`:

```python
if self.config.sigma_prior == "half_normal":
    sigma = pm.HalfNormal("sigma", sigma=2, shape=n_features)   # 定义但从未使用
else:
    sigma = pm.Exponential("sigma", lam=1, shape=n_features)    # 同上

chol, corr, stds = pm.LKJCholeskyCov(
    "chol", n=n_features, eta=self.config.lkj_eta,
    sd_dist=pm.Exponential.dist(1.0, shape=n_features),  # 使用此处的sd_dist
    compute_corr=True,
)
```

**影响**: sigma被采样但未参与 `beta = mu + (chol @ z.T).T` 计算。`LKJCholeskyCov` 使用自己的 `sd_dist=Exponential(1.0)`，与config的`sigma_prior`设置不一致。trace中多出无用的`sigma`变量。

**修复**: 将`config.sigma_prior`的分布传给`LKJCholeskyCov`的`sd_dist`。

### 1.2 收敛诊断

| 诊断项 | 阈值 | 实现评估 |
|--------|------|----------|
| R-hat max | < 1.1 | 正确：ArviZ DataTree提取，多维参数坐标展开 |
| ESS bulk min | > 400 | 正确：`method="bulk"` |
| ESS tail min | > 400 | 正确：`method="tail"` |
| Divergences | 任何>0则警告 | 正确 |
| Tree depth max | >=10则警告 | 正确 |

### 1.3 WTP与重要性

- **WTP**: 公式 `WTP = -beta_feature / beta_price`，正向价格系数过滤，极端值1%/99%剪裁 — 正确
- **重要性**: 公式 `Importance = Range_attr / sum(Range_all)`，effects coding恢复全部水平 — 正确

---

## 二、MNL引擎审查

| 检查项 | 状态 | 说明 |
|--------|------|------|
| statsmodels ConditionalLogit | 正确 | 标准实现 |
| 系数提取 | 正确 | 处理Series/ndarray两种类型 |
| McFadden R2 | 正确 | `1 - LL_model / LL_null` |
| AIC/BIC | 正确 | |
| 个体效用 | 正确 | MNL无个体异质性 |

### 发现的BUG

**P1: `get_model_fit()` 硬编码3方案假设 (line 214-215)**
```python
n_choice_sets = n_obs // 3 if n_obs >= 3 else 1
llnull = n_choice_sets * np.log(1.0 / 3.0)
```
如果方案数不是3，零模型似然出错。

**P1: `fit()` 收敛检测不可靠 (line 140)**
`converged = True` — 始终返回True，无法检测优化不收敛。

---

## 三、ISS-004 修复状态

**已修复**：`test_hb_convergence_validation.py:92` 列名已从 `respondent_id` 改为 `resp_id`，与HB引擎默认一致。

**仍有问题** — P0-BUG `test_hb_convergence_validation.py:338`：
```python
mnl_sign = np.sign(mnl_result.params.get(key, 0))  # MNLResult没有.params属性
```
`MNLResult`的属性是`population_mu`(dict)，应改为`mnl_result.population_mu.get(key, 0)`。

---

## 四、全部BUG汇总

| 编号 | 严重度 | 文件 | 行号 | 描述 |
|------|--------|------|------|------|
| BUG-001 | **P0** | `routes.py` | 105-106 | `hb_result.ess_min` 应为 `ess_bulk_min`/`ess_tail_min` — 生产API 500 |
| BUG-002 | **P0** | `test_hb_convergence_validation.py` | 338 | `mnl_result.params` 应为 `population_mu` |
| BUG-003 | **P0** | `hb_engine.py` | 149-162 | `sigma`变量为死代码，与`sigma_prior`配置脱节 |
| BUG-004 | P1 | `mnl_engine.py` | 214-215 | `get_model_fit()`硬编码3方案假设 |
| BUG-005 | P1 | `mnl_engine.py` | 140 | `converged = True` 无实际收敛检测 |
| BUG-006 | P2 | `importance.py` | 55 | 连续属性魔法数字 range=10.0 |
| BUG-007 | P2 | `wtp.py` | 86-113 | 仅计算与基准水平的WTP比较 |

---

## 五、参数恢复精度评估

基于合成数据规模和模型结构（20 resp × 8 tasks, 4 params），HB引擎应能达到业务标准（mu恢复误差≤10%）。

| 指标 | 业务阈值 | 测试实现 |
|------|----------|----------|
| mu 恢复误差 | ≤ 10% | `rel_err < 0.10` |
| 个体排序 | Kendall tau > 0.7 | `mean_tau > 0.7` |
| R-hat | < 1.1 | `rhat_max < 1.1` |
| ESS | > 400 | `ess_bulk_min > 400` |

---

## 六、总体评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 模型规范 | 良好 | 非中心化参数化、先验合理 |
| 诊断完整性 | 良好 | R-hat + ESS(bulk+tail) + divergences + tree_depth |
| 代码清晰度 | 中等 | BUG-003死代码降低可读性 |
| 测试覆盖 | 良好 | 模型构建、参数恢复、收敛、边界、性能基准 |

**关键结论**：
1. HB核心算法正确，非中心化参数化无误
2. 收敛诊断完整正确，R-hat<1.1 + ESS>400 双重阈值
3. **3个P0 BUG需修复**：BUG-001会直接导致分析API 500错误
4. ISS-004列名问题已修复
5. 参数恢复预期可满足10%误差标准
