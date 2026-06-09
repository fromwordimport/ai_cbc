# CBC数据分析系统 — 架构设计与实现方案

> **版本**：v1.0  
> **定位**：承接 CBC 问卷系统导出的标准数据，执行联合分析建模、结果解释与报告生成  
> **配套系统**：cbc-questionnaire-system（问卷生成）、consumer-simulation（消费者模拟）  
> **上游输入**：`cbc-questionnaire-system/04-CBC与模拟消费者集成方案.md` 定义的标准交换格式

---

## 一、系统定位与边界

### 1.1 在整体流程中的位置

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AI 消费者研究平台                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────────┐ │
│  │ 画像生成Agent│ → │ CBC问卷Agent │ → │    CBC数据分析Agent          │ │
│  │ (已有)       │    │ (已有)       │    │    【本文档】                │ │
│  └─────────────┘    └──────┬──────┘    └─────────────────────────────┘ │
│                            │                           │                │
│                            ▼                           ▼                │
│                     ┌──────────────┐          ┌──────────────┐         │
│                     │ 模拟消费者Agent│          │  联合分析引擎  │         │
│                     │ (填写问卷)    │          │  (建模+解读)   │         │
│                     └──────┬───────┘          └──────┬───────┘         │
│                            │                           │                │
│                            ▼                           ▼                │
│                     ┌──────────────┐          ┌──────────────┐         │
│                     │  原始回答库   │ ───────→ │  分析报告/洞察 │         │
│                     └──────────────┘          └──────────────┘         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心职责

| 职责 | 说明 | 产出 |
|------|------|------|
| **数据接入与清洗** | 接收问卷系统的标准导出数据，校验、转换、编码 | 长格式分析数据集 |
| **统计建模** | 执行 MNL / Mixed Logit / HB / Latent Class 模型 | 模型参数、收敛诊断 |
| **效用解析** | 提取部分效用值、属性重要性、WTP | 结构化结果表 |
| **市场模拟** | 基于估计的效用函数预测市场份额 | 情景对比表 |
| **LLM 解读** | 将统计结果翻译为业务语言，生成洞察 | 自然语言解释 |
| **报告合成** | 自动整合图表、表格、结论 | Markdown / HTML / PDF |

### 1.3 与上游系统的接口边界

- **输入**：`cbc-questionnaire-system` 通过 `/export` 接口提供的标准交换数据（JSON/CSV/Parquet）
- **不处理**：问卷设计、选择集生成、模拟消费者填写（由上游系统负责）
- **输出**：分析报告、可视化图表、API 查询接口

---

## 二、系统总体架构

### 2.1 数据流架构

```
┌──────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ 标准数据  │  →  │  数据预处理  │  →  │  模型拟合   │  →  │  结果解析   │
│ 导入      │     │  与校验      │     │  引擎       │     │  与计算     │
├──────────┤     ├─────────────┤     ├─────────────┤     ├─────────────┤
│ Schema   │     │ 长格式转换   │     │ MNL 基线    │     │ 部分效用值   │
│ 校验     │     │ 编码处理     │     │ HB 核心     │     │ 属性重要性   │
│ 完整性   │     │ 缺失值处理   │     │ 潜在类别    │     │ WTP 计算    │
│ 检查     │     │ 样本量评估   │     │ 混合Logit   │     │ 置信区间    │
└──────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                 │
                    ┌────────────────────────────────────────────┘
                    │
                    ▼
┌──────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ 业务洞察  │  ←  │  LLM 解读   │  ←  │  市场模拟   │  ←  │  收敛诊断   │
│ 报告      │     │  Agent      │     │  引擎       │     │  与校验     │
├──────────┤     ├─────────────┤     ├─────────────┤     ├─────────────┤
│ Markdown │     │ 结果翻译    │     │ 份额预测    │     │ R-hat 检查  │
│ 可视化   │     │ 异常解释    │     │ 竞争分析    │     │ 有效样本量  │
│ PDF 导出 │     │ 建议生成    │     │ 价格弹性    │     │ 模型比较    │
└──────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

### 2.2 模块划分

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       CBC数据分析系统                                    │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐ │
│  │  数据接入层      │  │  建模引擎层      │  │  结果计算层             │ │
│  │  (Data Loader)   │  │  (Model Engine)  │  │  (Result Processor)     │ │
│  │                  │  │                  │  │                         │ │
│  │ • Schema 校验    │  │ • MNL 模型       │  │ • 效用提取              │ │
│  │ • 长格式转换     │  │ • HB 模型(MCMC)  │  │ • 重要性计算            │ │
│  │ • 编码处理       │  │ • Latent Class   │  │ • WTP 计算              │ │
│  │ • 样本量评估     │  │ • Mixed Logit    │  │ • 置信区间              │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐ │
│  │  市场模拟层      │  │  LLM 交互层      │  │  报告生成层             │ │
│  │  (Simulator)     │  │  (LLM Agent)     │  │  (Report Builder)       │ │
│  │                  │  │                  │  │                         │ │
│  │ • 份额预测       │  │ • 自然语言查询   │  │ • 图表生成              │ │
│  │ • 情景对比       │  │ • 代码生成       │  │ • Markdown 合成         │ │
│  │ • 敏感度分析     │  │ • 结果解读       │  │ • PDF 导出              │ │
│  │ • 竞争分析       │  │ • 异常诊断       │  │ • 交互式 HTML           │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.3 核心处理流程

```
Phase 1: 数据接入与预处理
───────────────────────────
接收标准交换数据 → Schema 校验 → 构建长格式数据表 → 编码处理 → 样本量评估
                                                          ↓
                                                   数据质量报告

Phase 2: 模型拟合
─────────────────
自动选择模型策略 → MNL 基线 → HB 核心估计 → 收敛诊断 → 模型比较
                              ↓
                        潜在类别探索（可选）

Phase 3: 结果解析
─────────────────
提取部分效用值 → 计算属性重要性 → 计算 WTP → 构建结果对象

Phase 4: 市场模拟（按需）
─────────────────────────
定义竞争情景 → 计算预测效用 → 应用 Logit 规则 → 输出份额预测

Phase 5: LLM 解读与报告
───────────────────────
加载分析结果 → 生成业务解读 → 合成图表 → 输出结构化报告
```

---

## 三、数据标准化与接入

### 3.1 输入数据格式

分析系统接收来自问卷系统的**标准交换数据**，详细定义见 `cbc-questionnaire-system/04-CBC与模拟消费者集成方案.md` 第 3.3.b 节。

**核心输入包含三部分**：

```json
{
  "metadata": {          // 问卷元数据
    "attributes": [...], // 属性定义（类型、水平）
    "design_parameters": {...}
  },
  "choice_records": [...], // 选择记录（核心数据）
  "respondent_attributes": {...} // 受访者画像属性（可选）
}
```

### 3.2 内部标准数据格式（长表）

无论输入格式如何，分析系统内部统一转换为**长格式（Long Format）**：

```python
# 每行 = 一个受访者 × 一个选择集 × 一个概念
# 核心列定义

required_columns = {
    "resp_id": "str",           # 受访者唯一标识
    "resp_index": "int",        # 受访者索引（0-based）
    "task_id": "int",           # 选择集ID
    "task_index": "int",        # 选择集索引（0-based）
    "alt_id": "int",            # 选项在选择集中的索引
    "choice": "int",            # 是否被选中 (0/1)
    "none_option": "bool",      # 是否包含"都不选"
    # 属性列根据 metadata.attributes 动态生成
}
```

**示例长表**：

```
resp_id    task_id  alt_id  choice  brand_huawei  brand_xiaomi  price  storage_256gb  battery  charging
persona-1      1       0       0           1             0    3999              1     5000        66
persona-1      1       1       1           0             1    2999              0     5500       120
persona-1      1       2       0          -1            -1    5999              1     4500        33
persona-1      2       0       0          -1            -1    3999              0     5000       120
...
```

### 3.3 编码方案

分析系统支持以下编码方式，自动根据属性类型选择：

| 编码方式 | 适用类型 | 说明 | 参数数 |
|---------|---------|------|--------|
| **Effects Coding** | 分类变量（默认） | 参数和为0，便于解释 | k-1 |
| **Dummy Coding** | 分类变量 | 以参考水平为基准 | k-1 |
| **Continuous** | 连续/价格变量 | 原始值或标准化 | 1 |
| **Orthogonal Polynomial** | 有序变量 | 线性/二次/三次趋势 | k-1 |

**Effects Coding 示例（3水平品牌）**：

```python
# brand: huawei(0), xiaomi(1), apple(2)
# effects coding 生成 2 个变量

brand_encoding = {
    "huawei": [1, 0],
    "xiaomi": [0, 1],
    "apple":  [-1, -1]   # 参考水平，参数和为0
}
```

### 3.4 数据校验规则

```python
class DataValidator:
    """数据质量校验器"""
    
    validation_rules = [
        # 1. 属性定义完整性
        {
            "name": "attributes_complete",
            "check": "metadata.attributes is not empty",
            "severity": "ERROR",
            "message": "属性定义不能为空"
        },
        # 2. 每题必有一选
        {
            "name": "one_choice_per_task",
            "check": "sum(choice) == 1 per (resp_id, task_id)",
            "severity": "WARNING",
            "message": "存在未做选择或多选的题目"
        },
        # 3. 样本量充足性
        {
            "name": "sample_size_adequate",
            "check": "n_respondents * n_tasks >= n_params * 5",
            "severity": "WARNING",
            "message": "样本量可能不足，参数估计精度受限"
        },
        # 4. 属性水平覆盖
        {
            "name": "level_coverage",
            "check": "each level appears in at least 10% of tasks",
            "severity": "WARNING", 
            "message": "某些属性水平出现频率过低"
        },
        # 5. "都不选"比例检查
        {
            "name": "none_option_rate",
            "check": "none_chosen_rate < 50%",
            "severity": "WARNING",
            "message": "'都不选'比例过高，可能影响模型估计"
        }
    ]
```

---

## 四、自动建模流程

### 4.1 模型选择策略

系统根据数据特征自动推荐建模策略：

```
┌─────────────────────────────────────────────────────────────┐
│                      模型选择决策树                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  样本量 >= 100 且 属性数 <= 6？                             │
│       │                                                     │
│       ├── 是 → HB (Hierarchical Bayes) 【推荐】             │
│       │        • 个体层面效用估计                            │
│       │        • 多元正态异质性分布                          │
│       │        • 需要 MCMC 采样                              │
│       │                                                     │
│       └── 否 → 选择集数量 >= 12 每受访者？                  │
│                │                                            │
│                ├── 是 → Mixed Logit (MXL)                  │
│                │        • 随机参数Logit                      │
│                │        • 模拟积分估计                       │
│                │                                            │
│                └── 否 → MNL (Multinomial Logit)            │
│                         • 条件Logit基线                     │
│                         • 聚合层面估计                       │
│                                                             │
│  需要人群细分？ → Latent Class Analysis (LCA)              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 MNL 基线模型

**使用 `statsmodels` 或 `biogeme` 实现**：

```python
import pandas as pd
import statsmodels.api as sm
from statsmodels.discrete.discrete_choice import MNLogit

class MNLModel:
    """
    多项Logit基线模型
    用于快速获得聚合层面的偏好估计
    """
    
    def __init__(self, data: pd.DataFrame, attribute_cols: list[str]):
        self.data = data
        self.attribute_cols = attribute_cols
        self.model = None
        self.results = None
    
    def fit(self) -> "MNLModel":
        """
        拟合条件Logit模型
        
        数据格式要求：
        - 长格式，每行一个选项
        - choice 列：0/1 表示是否被选中
        - 按 (resp_id, task_id) 分组
        """
        # 构建设计矩阵和响应变量
        X = self.data[self.attribute_cols]
        y = self.data["choice"]
        
        # 使用条件Logit（需要按选择集分组）
        # statsmodels 的 ConditionalLogit 需要特殊格式
        self.model = MNLogit(y, X)
        self.results = self.model.fit(
            method="bfgs",
            maxiter=100,
            disp=False
        )
        return self
    
    def get_part_worths(self) -> pd.DataFrame:
        """提取部分效用值（参数估计）"""
        params = self.results.params
        conf_int = self.results.conf_int()
        
        return pd.DataFrame({
            "attribute": params.index,
            "coefficient": params.values,
            "std_err": self.results.bse.values,
            "z_value": self.results.tvalues.values,
            "p_value": self.results.pvalues.values,
            "ci_lower": conf_int.iloc[:, 0].values,
            "ci_upper": conf_int.iloc[:, 1].values,
            "significant": self.results.pvalues.values < 0.05
        })
    
    def summary(self) -> dict:
        """模型诊断摘要"""
        return {
            "log_likelihood": self.results.llf,
            "null_log_likelihood": self.results.llnull,
            "mc_fadden_r2": self.results.prsquared,
            "aic": self.results.aic,
            "bic": self.results.bic,
            "n_observations": self.results.nobs,
            "converged": self.results.mle_retvals.get("converged", False)
        }
```

### 4.3 分层贝叶斯（HB）—— 核心模型

**使用 `PyMC` 实现混合多项式Logit模型**：

```python
import pymc as pm
import numpy as np
import pytensor.tensor as pt

class HBModel:
    """
    分层贝叶斯 Mixed Logit 模型
    
    核心假设：
    - 每个受访者有独立的偏好系数 beta_i
    - beta_i ~ N(mu, Sigma)  （多元正态分布）
    - mu, Sigma 为总体超参数
    
    使用 NUTS 采样器进行后验推断
    """
    
    def __init__(
        self,
        data: pd.DataFrame,
        attribute_cols: list[str],
        resp_id_col: str = "resp_id",
        task_id_col: str = "task_id",
        choice_col: str = "choice"
    ):
        self.data = data
        self.attribute_cols = attribute_cols
        self.resp_id_col = resp_id_col
        self.task_id_col = task_id_col
        self.choice_col = choice_col
        
        # 预处理
        self._preprocess()
    
    def _preprocess(self):
        """构建模型所需的数据结构"""
        # 受访者映射
        self.resp_ids = self.data[self.resp_id_col].unique()
        self.n_resp = len(self.resp_ids)
        self.n_attrs = len(self.attribute_cols)
        
        # 构建响应索引
        self.data["resp_idx"] = self.data[self.resp_id_col].map(
            {rid: i for i, rid in enumerate(self.resp_ids)}
        )
        
        # 构建设计矩阵
        self.X = self.data[self.attribute_cols].values
        self.y = self.data[self.choice_col].values
        self.resp_idx = self.data["resp_idx"].values.astype(int)
        
        # 每个选择集的选项数量（用于 reshape）
        self.tasks = self.data.groupby([self.resp_id_col, self.task_id_col]).size()
        self.n_tasks_per_resp = self.data.groupby(self.resp_id_col)[self.task_id_col].nunique()
        
        # 构建数组索引，用于将长格式转为每个选择集的矩阵
        self._build_task_indices()
    
    def _build_task_indices(self):
        """
        构建任务索引，便于向量化计算
        
        将长格式数据按 (resp, task) 分组，每组是一个选择集
        在模型中需要计算每个选择集的 softmax 概率
        """
        self.task_groups = self.data.groupby([self.resp_id_col, self.task_id_col])
        self.n_tasks = len(self.task_groups)
        
        # 预计算每个任务的属性矩阵和选择结果
        self.task_X = []  # 每个任务的 X 矩阵
        self.task_y = []  # 每个任务的选择索引
        self.task_resp = []  # 每个任务所属受访者
        
        for (resp, task), group in self.task_groups:
            self.task_X.append(group[self.attribute_cols].values)
            chosen = group[group[self.choice_col] == 1].index[0] - group.index[0]
            self.task_y.append(chosen)
            self.task_resp.append(
                {rid: i for i, rid in enumerate(self.resp_ids)}[resp]
            )
    
    def build_model(self, prior_config: dict = None):
        """
        构建 PyMC 模型
        
        Parameters
        ----------
        prior_config : dict
            先验分布配置，默认使用弱信息先验
        """
        if prior_config is None:
            prior_config = {
                "mu_mu": 0,        # 总体均值先验均值
                "mu_sigma": 10,    # 总体均值先验标准差
                "sigma_alpha": 3,  # 总体标准差先验形状
                "sigma_beta": 1,   # 总体标准差先验速率
            }
        
        self.model = pm.Model()
        
        with self.model:
            # ── 总体超参数 ──
            # 总体均值向量
            mu = pm.Normal(
                "mu",
                mu=prior_config["mu_mu"],
                sigma=prior_config["mu_sigma"],
                shape=self.n_attrs
            )
            
            # 总体标准差（非中心化参数化提升采样效率）
            sigma = pm.HalfNormal("sigma", sigma=2, shape=self.n_attrs)
            
            # 总体相关性（使用 LKJ 先验）
            chol, corr, stds = pm.LKJCholeskyCov(
                "chol",
                n=self.n_attrs,
                eta=2.0,
                sd_dist=pm.Exponential.dist(1.0, shape=self.n_attrs)
            )
            
            # 协方差矩阵
            cov = pm.Deterministic("cov", chol @ chol.T)
            
            # ── 个体系数 ──
            # 非中心化参数化：beta_i = mu + chol @ z_i
            z = pm.Normal("z", mu=0, sigma=1, shape=(self.n_resp, self.n_attrs))
            beta = pm.Deterministic(
                "beta",
                mu + (chol @ z.T).T
            )
            
            # ── 似然函数 ──
            # 对每个选择集计算 softmax 概率
            log_probs = []
            
            for i in range(self.n_tasks):
                X_task = self.task_X[i]  # (n_alts, n_attrs)
                resp = self.task_resp[i]
                
                # 计算该任务下各选项的效用
                utilities = pm.math.dot(X_task, beta[resp])  # (n_alts,)
                
                # 计算被选中的概率（softmax）
                # 使用 log-softmax 数值稳定性更好
                log_prob = pm.math.log_softmax(utilities)[self.task_y[i]]
                log_probs.append(log_prob)
            
            # 总对数似然
            pm.Potential("log_likelihood", pm.math.sum(log_probs))
    
    def fit(
        self,
        n_draws: int = 1000,
        n_tune: int = 1000,
        n_chains: int = 4,
        target_accept: float = 0.9,
        **kwargs
    ) -> az.InferenceData:
        """
        运行 MCMC 采样
        
        Parameters
        ----------
        n_draws : int
            每链的采样次数
        n_tune : int
            预烧期（tuning）迭代次数
        n_chains : int
            并行链数
        target_accept : float
            NUTS 的目标接受率
        """
        with self.model:
            self.trace = pm.sample(
                draws=n_draws,
                tune=n_tune,
                chains=n_chains,
                target_accept=target_accept,
                return_inferencedata=True,
                **kwargs
            )
        return self.trace
    
    def get_individual_utilities(self) -> pd.DataFrame:
        """
        提取个体层面的效用估计（后验均值）
        
        Returns
        -------
        pd.DataFrame : (n_resp, n_attrs) 每个受访者的效用估计
        """
        beta_posterior = self.trace.posterior["beta"]
        beta_mean = beta_posterior.mean(dim=["chain", "draw"]).values
        
        return pd.DataFrame(
            beta_mean,
            index=self.resp_ids,
            columns=self.attribute_cols
        )
    
    def get_population_distribution(self) -> dict:
        """
        获取总体分布参数的后验摘要
        
        Returns
        -------
        dict : 包含 mu, sigma, cov 的后验统计量
        """
        import arviz as az
        
        summary = az.summary(self.trace, var_names=["mu", "sigma", "cov"])
        
        return {
            "mu": summary.loc[summary.index.str.startswith("mu")],
            "sigma": summary.loc[summary.index.str.startswith("sigma")],
            "cov": summary.loc[summary.index.str.startswith("cov")]
        }
    
    def convergence_diagnostics(self) -> dict:
        """
        收敛诊断
        
        Returns
        -------
        dict : R-hat, ESS 等诊断指标
        """
        import arviz as az
        
        rhat = az.rhat(self.trace, var_names=["mu", "sigma", "beta"])
        ess = az.ess(self.trace, var_names=["mu", "sigma", "beta"])
        
        return {
            "rhat_max": float(rhat.max().values),
            "rhat_by_param": rhat.to_dataframe(),
            "ess_min": float(ess.min().values),
            "ess_by_param": ess.to_dataframe(),
            "converged": float(rhat.max().values) < 1.1
        }
```

### 4.4 潜在类别模型（Latent Class）

```python
from sklearn.mixture import BayesianGaussianMixture

class LatentClassModel:
    """
    潜在类别分析
    
    基于 HB 估计的个体效用，使用高斯混合模型进行聚类
    自动尝试 2~6 个类别，根据 BIC 选择最优
    """
    
    def __init__(self, individual_utilities: pd.DataFrame):
        """
        Parameters
        ----------
        individual_utilities : pd.DataFrame
            HB 模型输出的个体效用矩阵 (n_resp × n_attrs)
        """
        self.util = individual_utilities
        self.best_model = None
        self.best_n_classes = None
    
    def fit_range(self, min_classes: int = 2, max_classes: int = 6) -> pd.DataFrame:
        """
        拟合多个类别数的模型，返回比较表
        
        Returns
        -------
        pd.DataFrame : 各模型的 BIC、AIC、对数似然
        """
        results = []
        
        for n in range(min_classes, max_classes + 1):
            model = BayesianGaussianMixture(
                n_components=n,
                covariance_type="full",
                n_init=10,
                max_iter=500,
                random_state=42
            )
            model.fit(self.util.values)
            
            results.append({
                "n_classes": n,
                "log_likelihood": model.lower_bound_,
                "aic": model.aic(self.util.values),
                "bic": model.bic(self.util.values),
                "converged": model.converged_
            })
            
            # 记录最优模型（按 BIC）
            if self.best_model is None or model.bic(self.util.values) < self.best_model.bic(self.util.values):
                self.best_model = model
                self.best_n_classes = n
        
        return pd.DataFrame(results)
    
    def get_class_profiles(self) -> pd.DataFrame:
        """获取各类别的均值效用 profile"""
        if self.best_model is None:
            raise ValueError("请先调用 fit_range()")
        
        return pd.DataFrame(
            self.best_model.means_,
            columns=self.util.columns,
            index=[f"Class_{i+1}" for i in range(self.best_n_classes)]
        )
    
    def get_membership_probs(self) -> pd.DataFrame:
        """获取每个受访者属于各类别的概率"""
        if self.best_model is None:
            raise ValueError("请先调用 fit_range()")
        
        probs = self.best_model.predict_proba(self.util.values)
        return pd.DataFrame(
            probs,
            index=self.util.index,
            columns=[f"Class_{i+1}" for i in range(self.best_n_classes)]
        )
    
    def get_class_sizes(self) -> pd.Series:
        """获取各类别的样本量占比"""
        labels = self.best_model.predict(self.util.values)
        return pd.Series(labels).value_counts(normalize=True).sort_index()
```

### 4.5 模型比较与选择

```python
class ModelComparer:
    """模型比较器"""
    
    @staticmethod
    def compare_models(models: dict[str, Any]) -> pd.DataFrame:
        """
        比较多个模型的拟合指标
        
        Parameters
        ----------
        models : dict
            {model_name: model_object}
        
        Returns
        -------
        pd.DataFrame : 模型比较表
        """
        comparisons = []
        
        for name, model in models.items():
            if hasattr(model, "summary"):
                summary = model.summary()
                comparisons.append({
                    "model": name,
                    "log_likelihood": summary.get("log_likelihood"),
                    "aic": summary.get("aic"),
                    "bic": summary.get("bic"),
                    "n_params": summary.get("n_params"),
                    "n_obs": summary.get("n_observations"),
                    "converged": summary.get("converged", "N/A")
                })
        
        df = pd.DataFrame(comparisons)
        
        # 标记推荐模型（最低 BIC）
        if "bic" in df.columns:
            df["recommended"] = df["bic"] == df["bic"].min()
        
        return df
```

---

## 五、效用后处理与重要性计算

### 5.1 属性重要性计算

```python
import numpy as np

class ImportanceCalculator:
    """
    属性重要性计算器
    
    核心逻辑：属性重要性 = 该属性各水平效用的极差 / 所有属性极差之和
    """
    
    @staticmethod
    def compute_importance(
        individual_utilities: pd.DataFrame,
        attribute_specs: dict[str, dict]
    ) -> pd.DataFrame:
        """
        计算每个受访者的属性重要性
        
        Parameters
        ----------
        individual_utilities : pd.DataFrame
            个体效用矩阵（编码后的参数）
        attribute_specs : dict
            属性规格说明，用于将编码参数映射回属性水平效用
            {
                "brand": {
                    "type": "categorical",
                    "levels": ["huawei", "xiaomi", "apple"],
                    "encoding": "effects"
                },
                "price": {
                    "type": "continuous",
                    "unit": "元"
                }
            }
        
        Returns
        -------
        pd.DataFrame : (n_resp, n_attributes) 属性重要性矩阵
        """
        importance_by_resp = []
        
        for resp_id, util_row in individual_utilities.iterrows():
            attr_ranges = {}
            
            for attr_name, spec in attribute_specs.items():
                if spec["type"] == "categorical":
                    # 从编码参数恢复各水平效用
                    level_utils = ImportanceCalculator._recover_level_utilities(
                        util_row, attr_name, spec
                    )
                    attr_ranges[attr_name] = level_utils.max() - level_utils.min()
                
                elif spec["type"] in ["continuous", "price"]:
                    # 连续变量：使用参数绝对值 × 属性范围
                    param = util_row.get(attr_name, 0)
                    attr_range = spec.get("range", [spec["levels"][0], spec["levels"][-1]])
                    attr_ranges[attr_name] = abs(param) * (attr_range[1] - attr_range[0])
            
            # 归一化
            total_range = sum(attr_ranges.values())
            if total_range > 0:
                importance = {k: v / total_range for k, v in attr_ranges.items()}
            else:
                importance = {k: 0 for k in attr_ranges}
            
            importance_by_resp.append(importance)
        
        return pd.DataFrame(importance_by_resp, index=individual_utilities.index)
    
    @staticmethod
    def _recover_level_utilities(
        util_row: pd.Series,
        attr_name: str,
        spec: dict
    ) -> np.ndarray:
        """
        从 effects coding 参数恢复各水平效用值
        
        effects coding 下，k 个水平有 k-1 个参数，
        第 k 个水平的效用 = -(其余参数之和)
        """
        n_levels = len(spec["levels"])
        params = []
        
        for i in range(n_levels - 1):
            param_name = f"{attr_name}_{i}"  # 或根据实际列名规则
            params.append(util_row.get(param_name, 0))
        
        # 恢复最后一个水平
        params.append(-sum(params))
        
        return np.array(params)
```

### 5.2 支付意愿（WTP）计算

```python
class WTPCalculator:
    """
    支付意愿计算器
    
    WTP = -beta_feature / beta_price
    
    注意：
    - 价格系数通常为负
    - 需要价格属性为连续变量
    - 对 categorical 属性，WTP 是水平间差异的货币等价
    """
    
    def __init__(self, individual_utilities: pd.DataFrame, price_col: str = "price"):
        self.util = individual_utilities
        self.price_col = price_col
        
        # 检查价格系数
        if price_col not in individual_utilities.columns:
            raise ValueError(f"价格列 '{price_col}' 不存在于效用矩阵中")
    
    def compute_wtp(
        self,
        feature_col: str,
        feature_type: str = "continuous",
        level_diff: float = None
    ) -> pd.Series:
        """
        计算某属性的支付意愿
        
        Parameters
        ----------
        feature_col : str
            属性列名
        feature_type : str
            "continuous" 或 "categorical"
        level_diff : float
            分类属性时，水平间的效用差异（用于计算货币等价）
        
        Returns
        -------
        pd.Series : 每个受访者的 WTP
        """
        beta_price = self.util[self.price_col]
        beta_feature = self.util[feature_col]
        
        # 检查价格系数符号
        if (beta_price > 0).any():
            print("警告：部分受访者的价格系数为正，WTP 计算可能无意义")
        
        if feature_type == "continuous":
            # 连续变量：单位变化的 WTP
            wtp = -beta_feature / beta_price
        else:
            # 分类变量：给定水平差异的 WTP
            if level_diff is None:
                raise ValueError("分类属性需要提供 level_diff")
            wtp = -level_diff / beta_price
        
        # 过滤异常值（WTP 过大可能是价格系数接近0导致）
        wtp = wtp[np.abs(wtp) < wtp.quantile(0.99)]
        
        return wtp
    
    def compute_all_wtp(
        self,
        attribute_specs: dict[str, dict]
    ) -> pd.DataFrame:
        """
        批量计算所有属性的 WTP
        
        Returns
        -------
        pd.DataFrame : WTP 统计摘要
        """
        results = []
        
        for attr_name, spec in attribute_specs.items():
            if attr_name == self.price_col:
                continue
            
            if spec["type"] == "continuous":
                wtp = self.compute_wtp(attr_name, "continuous")
                results.append({
                    "attribute": attr_name,
                    "comparison": f"每单位 {spec.get('unit', '')}",
                    "wtp_mean": wtp.mean(),
                    "wtp_median": wtp.median(),
                    "wtp_std": wtp.std(),
                    "wtp_ci_lower": wtp.quantile(0.025),
                    "wtp_ci_upper": wtp.quantile(0.975)
                })
            
            elif spec["type"] == "categorical":
                levels = spec["levels"]
                # 计算各水平间的 WTP（以最低水平为基准）
                base_level = levels[0]
                for level in levels[1:]:
                    # 这里需要根据编码方式计算水平间效用差
                    # 简化示意：假设水平效用已恢复
                    level_diff = 1.0  # 实际需要计算
                    wtp = self.compute_wtp(attr_name, "categorical", level_diff)
                    results.append({
                        "attribute": attr_name,
                        "comparison": f"{level} vs {base_level}",
                        "wtp_mean": wtp.mean(),
                        "wtp_median": wtp.median(),
                        "wtp_std": wtp.std(),
                        "wtp_ci_lower": wtp.quantile(0.025),
                        "wtp_ci_upper": wtp.quantile(0.975)
                    })
        
        return pd.DataFrame(results)
```

### 5.3 结果聚合与置信区间

```python
class ResultAggregator:
    """结果聚合器：计算群体层面的统计量"""
    
    @staticmethod
    def aggregate_results(
        individual_results: pd.DataFrame,
        confidence: float = 0.95
    ) -> pd.DataFrame:
        """
        聚合个体结果到群体层面
        
        Parameters
        ----------
        individual_results : pd.DataFrame
            个体层面结果（如重要性、WTP）
        confidence : float
            置信水平
        
        Returns
        -------
        pd.DataFrame : 群体统计摘要
        """
        alpha = 1 - confidence
        lower_q = alpha / 2
        upper_q = 1 - alpha / 2
        
        summary = pd.DataFrame({
            "mean": individual_results.mean(),
            "median": individual_results.median(),
            "std": individual_results.std(),
            "min": individual_results.min(),
            "max": individual_results.max(),
            "q25": individual_results.quantile(0.25),
            "q75": individual_results.quantile(0.75),
            f"ci_{int(confidence*100)}_lower": individual_results.quantile(lower_q),
            f"ci_{int(confidence*100)}_upper": individual_results.quantile(upper_q)
        })
        
        return summary
```

---

## 六、市场模拟器

### 6.1 市场份额预测

```python
class MarketSimulator:
    """
    市场模拟器
    
    基于估计的个体效用函数，预测不同产品配置的市场份额
    """
    
    def __init__(self, individual_utilities: pd.DataFrame, attribute_specs: dict):
        self.util = individual_utilities
        self.specs = attribute_specs
    
    def simulate_share(
        self,
        scenarios: list[dict[str, Any]],
        rule: str = "logit",
        none_option: bool = True,
        none_utility: float = 0.0
    ) -> pd.DataFrame:
        """
        模拟市场份额
        
        Parameters
        ----------
        scenarios : list[dict]
            竞争情景，每个情景是一个产品配置
            [
                {"name": "产品A", "brand": "huawei", "price": 3999, ...},
                {"name": "产品B", "brand": "xiaomi", "price": 2999, ...}
            ]
        rule : str
            "logit" - 标准logit份额预测
            "first_choice" - 首选模型（每人选效用最高的）
        none_option : bool
            是否包含"都不选"选项
        none_utility : float
            "都不选"选项的效用值
        
        Returns
        -------
        pd.DataFrame : 各情景的预测份额
        """
        n_resp = len(self.util)
        n_scenarios = len(scenarios)
        
        # 构建情景的设计矩阵
        scenario_matrix = self._build_scenario_matrix(scenarios)
        
        # 计算每个受访者对各情景的效用
        utilities = self.util.values @ scenario_matrix.T  # (n_resp, n_scenarios)
        
        if none_option:
            # 添加"都不选"选项
            none_col = np.full((n_resp, 1), none_utility)
            utilities = np.hstack([utilities, none_col])
        
        # 应用选择规则
        if rule == "logit":
            shares = self._logit_rule(utilities)
        elif rule == "first_choice":
            shares = self._first_choice_rule(utilities)
        else:
            raise ValueError(f"不支持的选择规则: {rule}")
        
        # 构建结果
        result = pd.DataFrame({
            "scenario": [s["name"] for s in scenarios] + (["none"] if none_option else []),
            "predicted_share": shares.mean(axis=0),
            "share_std": shares.std(axis=0),
            "share_ci_lower": np.percentile(shares, 2.5, axis=0),
            "share_ci_upper": np.percentile(shares, 97.5, axis=0)
        })
        
        return result
    
    def _build_scenario_matrix(self, scenarios: list[dict]) -> np.ndarray:
        """将情景配置转换为设计矩阵"""
        matrices = []
        
        for scenario in scenarios:
            row = []
            for attr_name, spec in self.specs.items():
                value = scenario.get(attr_name)
                
                if spec["type"] == "categorical":
                    # effects coding
                    levels = spec["levels"]
                    idx = levels.index(value)
                    n_levels = len(levels)
                    
                    encoding = []
                    for i in range(n_levels - 1):
                        if i == idx:
                            encoding.append(1)
                        elif idx == n_levels - 1:  # 参考水平
                            encoding.append(-1)
                        else:
                            encoding.append(0)
                    row.extend(encoding)
                
                elif spec["type"] in ["continuous", "price"]:
                    row.append(value)
            
            matrices.append(row)
        
        return np.array(matrices)
    
    def _logit_rule(self, utilities: np.ndarray) -> np.ndarray:
        """Logit 选择规则"""
        exp_util = np.exp(utilities - utilities.max(axis=1, keepdims=True))
        shares = exp_util / exp_util.sum(axis=1, keepdims=True)
        return shares
    
    def _first_choice_rule(self, utilities: np.ndarray) -> np.ndarray:
        """首选模型"""
        choices = np.argmax(utilities, axis=1)
        n = utilities.shape[1]
        shares = np.zeros((len(choices), n))
        shares[np.arange(len(choices)), choices] = 1
        return shares
    
    def sensitivity_analysis(
        self,
        base_scenario: dict,
        attribute: str,
        value_range: list,
        competitors: list[dict] = None
    ) -> pd.DataFrame:
        """
        价格/属性敏感度分析
        
        变动某个属性的值，观察份额变化
        """
        results = []
        
        for value in value_range:
            scenario = base_scenario.copy()
            scenario[attribute] = value
            
            scenarios = [scenario]
            if competitors:
                scenarios.extend(competitors)
            
            shares = self.simulate_share(scenarios)
            base_share = shares[shares["scenario"] == base_scenario["name"]]["predicted_share"].values[0]
            
            results.append({
                attribute: value,
                "predicted_share": base_share,
                "share_change": base_share - results[-1]["predicted_share"] if results else 0
            })
        
        return pd.DataFrame(results)
```

### 6.2 自然语言情景接口

```python
class NLScenarioParser:
    """
    自然语言情景解析器
    
    将用户的自然语言描述转换为结构化情景
    由 LLM 驱动
    """
    
    def __init__(self, attribute_specs: dict):
        self.specs = attribute_specs
    
    def parse(self, nl_description: str) -> list[dict]:
        """
        解析自然语言描述
        
        示例输入：
        "如果我推出一款售价2999元、带256GB存储的华为手机，
         与小米3999元512GB、苹果5999元256GB竞争"
        
        输出：
        [
            {"name": "我的产品", "brand": "huawei", "price": 2999, "storage": "256GB"},
            {"name": "竞品A", "brand": "xiaomi", "price": 3999, "storage": "512GB"},
            {"name": "竞品B", "brand": "apple", "price": 5999, "storage": "256GB"}
        ]
        """
        # 实际实现由 LLM Agent 调用
        # 这里定义接口契约
        
        # LLM Prompt 模板：
        prompt = f"""
        将以下自然语言描述解析为结构化产品配置。
        
        可用属性及水平：
        {json.dumps(self.specs, ensure_ascii=False, indent=2)}
        
        用户描述：{nl_description}
        
        请输出 JSON 数组，每个元素包含：
        - name: 产品名称
        - 各属性值（必须在可用水平中）
        
        只输出 JSON，不要其他内容。
        """
        
        # 由 LLM Agent 执行并返回
        raise NotImplementedError("由 LLM Agent 实现")
```

---

## 七、LLM 驱动的交互与分析对话

### 7.1 Agent 工具设计

基于 LangChain 构建分析 Agent，赋予以下工具：

```python
from langchain.agents import Tool, AgentExecutor
from langchain_core.language_models import BaseLanguageModel

class CBCAnalysisAgent:
    """
    CBC 数据分析 Agent
    
    提供自然语言接口，让用户通过对话方式探索数据
    """
    
    def __init__(
        self,
        llm: BaseLanguageModel,
        data_loader: DataLoader,
        model_engine: ModelEngine,
        result_processor: ResultProcessor,
        simulator: MarketSimulator
    ):
        self.llm = llm
        self.data_loader = data_loader
        self.model_engine = model_engine
        self.result_processor = result_processor
        self.simulator = simulator
        
        self.tools = self._build_tools()
        self.agent = self._build_agent()
    
    def _build_tools(self) -> list[Tool]:
        """构建 Agent 可用的工具集"""
        
        return [
            Tool(
                name="load_data",
                func=self._tool_load_data,
                description="加载 CBC 数据文件。输入：文件路径（CSV/JSON/Parquet）"
            ),
            Tool(
                name="get_data_summary",
                func=self._tool_data_summary,
                description="获取当前加载数据的摘要统计。无需参数。"
            ),
            Tool(
                name="fit_model",
                func=self._tool_fit_model,
                description="""拟合统计模型。输入：模型类型（"mnl"/"hb"/"latent_class"）。
                示例：fit_model("hb")"""
            ),
            Tool(
                name="get_model_summary",
                func=self._tool_model_summary,
                description="获取当前模型的诊断信息。无需参数。"
            ),
            Tool(
                name="plot_importance",
                func=self._tool_plot_importance,
                description="生成属性重要性条形图。输入：可选的排序方式（"mean"/"median"）。"
            ),
            Tool(
                name="get_utilities",
                func=self._tool_get_utilities,
                description="获取部分效用值。输入：属性名（可选，不填返回全部）。"
            ),
            Tool(
                name="compute_wtp",
                func=self._tool_compute_wtp,
                description="""计算支付意愿。输入：属性名。
                示例：compute_wtp("storage")"""
            ),
            Tool(
                name="simulate_market",
                func=self._tool_simulate_market,
                description="""模拟市场份额。输入：JSON 格式的情景数组。
                示例：simulate_market('[{"name":"产品A","brand":"huawei","price":3999}]')"""
            ),
            Tool(
                name="run_python",
                func=self._tool_run_python,
                description="""执行 Python 代码。输入：代码字符串。
                用于自定义分析。示例：run_python("import pandas; df.head()")"""
            ),
            Tool(
                name="generate_report",
                func=self._tool_generate_report,
                description="生成分析报告。输入：报告类型（"full"/"summary"/"market_sim"）。"
            )
        ]
    
    def _tool_load_data(self, path: str) -> str:
        """加载数据工具"""
        try:
            self.data_loader.load(path)
            summary = self.data_loader.get_summary()
            return f"数据加载成功！\n受访者数: {summary['n_respondents']}\n选择集数: {summary['n_choice_sets']}\n总记录数: {summary['n_records']}"
        except Exception as e:
            return f"数据加载失败: {str(e)}"
    
    def _tool_fit_model(self, model_type: str) -> str:
        """拟合模型工具"""
        try:
            if model_type.lower() == "mnl":
                self.model_engine.fit_mnl()
            elif model_type.lower() == "hb":
                self.model_engine.fit_hb()
            elif model_type.lower() == "latent_class":
                self.model_engine.fit_latent_class()
            else:
                return f"不支持的模型类型: {model_type}"
            
            return f"{model_type.upper()} 模型拟合完成！"
        except Exception as e:
            return f"模型拟合失败: {str(e)}"
    
    def _tool_model_summary(self) -> str:
        """模型摘要工具"""
        if not self.model_engine.has_model():
            return "请先拟合模型"
        
        summary = self.model_engine.get_summary()
        
        # 格式化输出
        lines = ["=== 模型诊断摘要 ==="]
        lines.append(f"Log-Likelihood: {summary['log_likelihood']:.2f}")
        lines.append(f"McFadden R²: {summary['mc_fadden_r2']:.4f}")
        lines.append(f"AIC: {summary['aic']:.2f}")
        lines.append(f"BIC: {summary['bic']:.2f}")
        
        if "rhat_max" in summary:
            lines.append(f"R-hat (max): {summary['rhat_max']:.4f}")
            lines.append(f"收敛状态: {'✓ 已收敛' if summary['converged'] else '✗ 未收敛'}")
        
        return "\n".join(lines)
    
    def _tool_plot_importance(self, sort_by: str = "mean") -> str:
        """生成重要性图表"""
        importance = self.result_processor.get_attribute_importance()
        fig = self.result_processor.plot_importance(importance, sort_by=sort_by)
        
        # 保存图表并返回路径
        path = "/tmp/importance_plot.png"
        fig.savefig(path)
        return f"属性重要性图表已生成: {path}"
    
    def _tool_simulate_market(self, scenarios_json: str) -> str:
        """市场模拟工具"""
        import json
        scenarios = json.loads(scenarios_json)
        result = self.simulator.simulate_share(scenarios)
        
        lines = ["=== 市场份额预测 ==="]
        for _, row in result.iterrows():
            lines.append(f"{row['scenario']}: {row['predicted_share']:.1%} (±{row['share_std']:.1%})")
        
        return "\n".join(lines)
    
    def _tool_run_python(self, code: str) -> str:
        """执行 Python 代码"""
        import io
        import sys
        
        # 在安全环境中执行
        stdout = io.StringIO()
        stderr = io.StringIO()
        
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout, stderr
        
        try:
            # 提供局部变量访问
            local_vars = {
                "data": getattr(self.data_loader, "data", None),
                "model": getattr(self.model_engine, "model", None),
                "results": getattr(self.result_processor, "results", None),
                "pd": pd,
                "np": np
            }
            exec(code, {"__builtins__": __builtins__}, local_vars)
            output = stdout.getvalue()
            return output or "代码执行成功（无输出）"
        except Exception as e:
            return f"执行错误: {str(e)}\n{stderr.getvalue()}"
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
    
    def chat(self, user_message: str) -> str:
        """
        处理用户消息
        
        示例对话：
        用户: "查看价格属性的系数和显著性"
        Agent: "正在查询..."
        → 调用 get_utilities("price")
        → LLM 解释: "价格系数为-0.35，意味着价格每上涨1元，效用下降0.35，显著（p<0.001）"
        """
        return self.agent.run(user_message)
```

### 7.2 对话示例

```markdown
> 用户：加载数据文件 "cbc_results.csv"
> Agent：数据加载成功！受访者数: 200, 选择集数: 12, 总记录数: 7200

> 用户：拟合 HB 模型
> Agent：HB 模型拟合完成！MCMC 采样 4 链 × 1000 次，预计耗时 3-5 分钟...
> Agent：模型已收敛（R-hat max = 1.02）

> 用户：查看价格属性的系数和显著性
> Agent：
> 【统计结果】
> - 价格系数均值: -0.0035 (元)
> - 95% 置信区间: [-0.0042, -0.0028]
> - 后验概率 < 0 的比例: 100%
> 
> 【业务解读】
> 价格系数为负且显著，说明消费者确实对价格敏感。
> 价格每上涨 100 元，平均效用下降 0.35 个单位。
> 在你的样本中，所有 200 个模拟消费者的价格系数均为负值，
> 这表明不存在"价格不敏感"的细分群体。

> 用户：计算各属性的重要性
> Agent：
> 【属性重要性排序】
> 1. 价格: 45.2% (±8.3%)
> 2. 品牌: 23.8% (±5.1%)
> 3. 充电功率: 15.3% (±4.2%)
> 4. 存储容量: 11.2% (±3.8%)
> 5. 电池容量: 4.5% (±2.1%)
> 
> 【洞察】
> 价格是最重要的决策因素，占据近半的决策权重。
> 品牌次之，说明消费者有明显的品牌偏好差异。
> 电池容量的重要性最低，可能因为当前产品已能满足基本需求。

> 用户：如果我推出一款售价 2999 元的华为 256GB 手机，
>      与小米 3999 元 512GB、苹果 4999 元 256GB 竞争，份额如何？
> Agent：
> 【竞争情景分析】
> ┌─────────────┬──────────┬─────────┬─────────┐
> │   产品      │  价格    │ 预测份额 │ 份额区间 │
> ├─────────────┼──────────┼─────────┼─────────┤
> │ 华为 256GB  │ ¥2,999   │  38.5%  │ 34%-43% │
> │ 小米 512GB  │ ¥3,999   │  31.2%  │ 27%-35% │
> │ 苹果 256GB  │ ¥4,999   │  22.8%  │ 19%-27% │
> │ 都不选      │    -     │   7.5%  │  5%-10% │
> └─────────────┴──────────┴─────────┴─────────┘
> 
> 【关键发现】
> 你的产品在价格敏感型消费者中具有优势，预计获得最高份额。
> 但苹果凭借其品牌溢价，即使价格高 2000 元，仍能吸引约 23% 的消费者。
> 建议：考虑在 2999 价位提供更差异化的存储配置以扩大优势。
```

---

## 八、自动报告生成

### 8.1 报告结构模板

```python
class ReportBuilder:
    """
    分析报告生成器
    
    自动整合分析过程中的所有输出，生成结构化报告
    """
    
    def __init__(self):
        self.sections = []
    
    def build_full_report(
        self,
        data_summary: dict,
        model_results: dict,
        importance: pd.DataFrame,
        wtp: pd.DataFrame,
        market_sim: pd.DataFrame = None,
        persona_cross: pd.DataFrame = None
    ) -> str:
        """
        生成完整分析报告
        
        Returns
        -------
        str : Markdown 格式的报告
        """
        sections = []
        
        # 1. 封面与概述
        sections.append(self._build_cover(data_summary))
        
        # 2. 数据概况
        sections.append(self._build_data_overview(data_summary))
        
        # 3. 模型诊断
        sections.append(self._build_model_diagnostics(model_results))
        
        # 4. 属性重要性与效用
        sections.append(self._build_importance_section(importance))
        
        # 5. 支付意愿
        sections.append(self._build_wtp_section(wtp))
        
        # 6. 市场模拟（可选）
        if market_sim is not None:
            sections.append(self._build_market_sim_section(market_sim))
        
        # 7. 人群细分（可选）
        if persona_cross is not None:
            sections.append(self._build_segment_section(persona_cross))
        
        # 8. 结论与建议
        sections.append(self._build_conclusions())
        
        return "\n\n---\n\n".join(sections)
    
    def _build_cover(self, summary: dict) -> str:
        return f"""# CBC 联合分析报告

> **生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M")}  
> **样本量**: {summary['n_respondents']} 位受访者  
> **选择集数**: {summary['n_choice_sets']} 个/人  
> **模型类型**: Hierarchical Bayes

---

## 执行摘要

本报告基于离散选择实验（CBC）数据，通过分层贝叶斯模型估计了消费者的属性偏好结构。
分析共涉及 **{summary['n_attributes']}** 个属性，**{summary['n_levels']}** 个水平。
关键发现将在各章节详细阐述。
"""
    
    def _build_importance_section(self, importance: pd.DataFrame) -> str:
        """构建属性重要性章节"""
        # 生成图表
        fig = self._plot_importance(importance)
        chart_path = "/tmp/importance.png"
        fig.savefig(chart_path)
        
        # 排序
        imp_sorted = importance.sort_values("mean", ascending=False)
        
        lines = ["## 三、属性重要性分析\n"]
        lines.append("![属性重要性](importance.png)\n")
        lines.append("### 3.1 重要性排序\n")
        lines.append("| 排名 | 属性 | 重要性(%) | 标准差 | 95% 置信区间 |")
        lines.append("|------|------|-----------|--------|-------------|")
        
        for i, (attr, row) in enumerate(imp_sorted.iterrows(), 1):
            lines.append(
                f"| {i} | {attr} | {row['mean']:.1%} | {row['std']:.1%} | "
                f"[{row['ci_95_lower']:.1%}, {row['ci_95_upper']:.1%}] |"
            )
        
        lines.append("\n### 3.2 关键洞察\n")
        
        # 由 LLM 生成洞察（或通过规则模板）
        top_attr = imp_sorted.index[0]
        top_imp = imp_sorted.iloc[0]["mean"]
        
        lines.append(
            f"- **{top_attr}** 是最重要的决策因素，占据 **{top_imp:.1%}** 的决策权重，"
            f"显著高于其他属性。"
        )
        
        if len(imp_sorted) > 1:
            second_attr = imp_sorted.index[1]
            second_imp = imp_sorted.iloc[1]["mean"]
            lines.append(
                f"- **{second_attr}** 位居第二（{second_imp:.1%}），"
                f"与 {top_attr} 合计解释了 {(top_imp + second_imp):.1%} 的偏好差异。"
            )
        
        return "\n".join(lines)
    
    def _build_wtp_section(self, wtp: pd.DataFrame) -> str:
        """构建 WTP 章节"""
        lines = ["## 四、支付意愿（Willingness to Pay）\n"]
        lines.append("> 支付意愿表示消费者愿意为某项属性改进支付的金额。\n")
        lines.append("| 属性对比 | WTP 均值 | WTP 中位数 | 95% 置信区间 |")
        lines.append("|----------|----------|------------|-------------|")
        
        for _, row in wtp.iterrows():
            lines.append(
                f"| {row['comparison']} | ¥{row['wtp_mean']:.0f} | "
                f"¥{row['wtp_median']:.0f} | "
                f"[¥{row['wtp_ci_lower']:.0f}, ¥{row['wtp_ci_upper']:.0f}] |"
            )
        
        return "\n".join(lines)
    
    def export_pdf(self, markdown_content: str, output_path: str):
        """导出 PDF 报告"""
        import pypandoc
        
        pypandoc.convert_text(
            markdown_content,
            "pdf",
            format="md",
            outputfile=output_path,
            extra_args=["--template=default", "--toc"]
        )
```

### 8.2 可视化规范

```python
import matplotlib.pyplot as plt
import seaborn as sns

class CBCVisualizer:
    """CBC 分析专用可视化"""
    
    @staticmethod
    def plot_importance(
        importance: pd.DataFrame,
        sort_by: str = "mean",
        figsize: tuple = (10, 6)
    ) -> plt.Figure:
        """
        属性重要性条形图
        
        带误差线显示置信区间
        """
        fig, ax = plt.subplots(figsize=figsize)
        
        data = importance.sort_values(sort_by, ascending=True)
        y_pos = range(len(data))
        
        # 绘制条形
        ax.barh(
            y_pos,
            data["mean"],
            xerr=[
                data["mean"] - data["ci_95_lower"],
                data["ci_95_upper"] - data["mean"]
            ],
            capsize=5,
            color="steelblue",
            alpha=0.8
        )
        
        ax.set_yticks(y_pos)
        ax.set_yticklabels(data.index)
        ax.set_xlabel("Importance (%)")
        ax.set_title("Attribute Importance (with 95% CI)")
        ax.axvline(x=0, color="black", linewidth=0.5)
        
        # 添加数值标签
        for i, (idx, row) in enumerate(data.iterrows()):
            ax.text(
                row["mean"] + 0.01,
                i,
                f"{row['mean']:.1%}",
                va="center",
                fontsize=9
            )
        
        plt.tight_layout()
        return fig
    
    @staticmethod
    def plot_part_worths(
        utilities: pd.DataFrame,
        attribute: str,
        level_labels: list[str] = None
    ) -> plt.Figure:
        """
        部分效用值分布图（蜂群图或小提琴图）
        """
        fig, ax = plt.subplots(figsize=(8, 5))
        
        # 提取该属性的各水平效用
        level_data = []
        for col in utilities.columns:
            if col.startswith(attribute):
                level_data.append(utilities[col].values)
        
        # 小提琴图
        parts = ax.violinplot(level_data, showmeans=True, showmedians=True)
        
        if level_labels:
            ax.set_xticks(range(1, len(level_labels) + 1))
            ax.set_xticklabels(level_labels)
        
        ax.set_ylabel("Part-Worth Utility")
        ax.set_title(f"Distribution of Part-Worth Utilities: {attribute}")
        ax.axhline(y=0, color="red", linestyle="--", alpha=0.5)
        
        return fig
    
    @staticmethod
    def plot_market_simulation(
        sim_results: pd.DataFrame
    ) -> plt.Figure:
        """市场份额预测图"""
        fig, ax = plt.subplots(figsize=(8, 5))
        
        colors = plt.cm.Set3(range(len(sim_results)))
        bars = ax.bar(
            sim_results["scenario"],
            sim_results["predicted_share"],
            yerr=sim_results["share_std"],
            capsize=5,
            color=colors,
            alpha=0.8
        )
        
        ax.set_ylabel("Predicted Market Share")
        ax.set_title("Market Share Simulation")
        ax.set_ylim(0, max(sim_results["predicted_share"]) * 1.3)
        
        # 添加数值标签
        for bar, share in zip(bars, sim_results["predicted_share"]):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"{share:.1%}",
                ha="center",
                fontsize=10
            )
        
        return fig
    
    @staticmethod
    def plot_convergence(
        trace,
        var_names: list[str] = None
    ) -> plt.Figure:
        """MCMC 收敛诊断图（trace plot）"""
        import arviz as az
        
        if var_names is None:
            var_names = ["mu"]
        
        fig = az.plot_trace(trace, var_names=var_names, figsize=(12, 8))
        plt.suptitle("MCMC Convergence Diagnostics")
        return fig
```

---

## 九、验证与可靠性保障

### 9.1 基准测试

```python
class BenchmarkValidator:
    """
    基准验证器
    
    使用已知真值的模拟数据，验证 Python 实现与 Sawtooth 结果的一致性
    """
    
    @staticmethod
    def generate_synthetic_data(
        n_resp: int = 500,
        n_tasks: int = 12,
        n_alts: int = 3,
        true_params: dict = None
    ) -> tuple[pd.DataFrame, dict]:
        """
        生成已知参数的模拟数据
        
        Parameters
        ----------
        true_params : dict
            真实参数值，用于验证估计准确性
            {
                "mu": [0.5, -0.3, 1.2, ...],  # 总体均值
                "sigma": [0.8, 0.5, 1.0, ...]  # 总体标准差
            }
        
        Returns
        -------
        data : 模拟的选择数据
        true_params : 用于生成数据的真实参数
        """
        # 使用已知效用函数生成选择数据
        # ... 实现略
        pass
    
    @staticmethod
    def validate_implementation(
        model_results: dict,
        true_params: dict,
        tolerance: float = 0.1
    ) -> dict:
        """
        验证估计结果与真实参数的偏差
        
        Returns
        -------
        dict : 验证报告
        """
        report = {
            "mu_bias": np.abs(model_results["mu"] - true_params["mu"]).mean(),
            "mu_correlation": np.corrcoef(model_results["mu"], true_params["mu"])[0, 1],
            "sigma_bias": np.abs(model_results["sigma"] - true_params["sigma"]).mean(),
            "within_tolerance": None
        }
        
        report["within_tolerance"] = (
            report["mu_bias"] < tolerance and
            report["sigma_bias"] < tolerance
        )
        
        return report
```

### 9.2 LLM 输出审查

```python
class CodeSafetyChecker:
    """
    LLM 生成代码的安全检查器
    
    所有由 LLM 生成的代码需经过沙盒试运行
    """
    
    forbidden_patterns = [
        "os.system", "subprocess", "eval(", "exec(",
        "__import__", "open(", "write", "delete"
    ]
    
    required_assertions = [
        "系数符号检查：价格系数应为负",
        "份额和检查：市场份额之和应为 100%",
        "概率检查：预测概率应在 [0, 1] 区间"
    ]
    
    @classmethod
    def check_code(cls, code: str) -> tuple[bool, list[str]]:
        """
        检查代码安全性
        
        Returns
        -------
        (is_safe, warnings)
        """
        warnings = []
        
        for pattern in cls.forbidden_patterns:
            if pattern in code:
                warnings.append(f"发现潜在危险操作: {pattern}")
        
        return len(warnings) == 0, warnings
    
    @classmethod
    def run_sandbox(cls, code: str, test_data: dict) -> dict:
        """
        在沙盒环境中执行代码并验证
        
        Returns
        -------
        dict : {success, output, errors, assertions_passed}
        """
        # 使用受限的 exec 环境
        # 注入测试数据，运行代码，检查结果
        pass
```

### 9.3 单元测试规范

```python
# tests/test_models.py

import pytest
import numpy as np
import pandas as pd

class TestHBModel:
    """HB 模型单元测试"""
    
    def test_convergence(self, sample_data):
        """测试模型收敛"""
        model = HBModel(sample_data, attribute_cols=["price", "brand"])
        model.build_model()
        trace = model.fit(n_draws=100, n_tune=100, n_chains=2)
        
        diagnostics = model.convergence_diagnostics()
        assert diagnostics["converged"], "模型未收敛"
        assert diagnostics["rhat_max"] < 1.1, f"R-hat 过高: {diagnostics['rhat_max']}"
    
    def test_price_coefficient_sign(self, sample_data):
        """测试价格系数符号"""
        model = HBModel(sample_data, attribute_cols=["price", "brand"])
        model.build_model()
        trace = model.fit(n_draws=100, n_tune=100, n_chains=2)
        
        mu_price = trace.posterior["mu"].sel({"mu_dim_0": 0}).mean()
        assert mu_price < 0, "价格系数应为负值"
    
    def test_probability_bounds(self, sample_data):
        """测试预测概率边界"""
        # 模拟结果应在 [0, 1] 区间
        pass
    
    def test_importance_sum_to_one(self, sample_data):
        """测试重要性之和为1"""
        model = HBModel(sample_data, attribute_cols=["price", "brand", "storage"])
        # ... 拟合模型
        
        importance = ImportanceCalculator.compute_importance(
            model.get_individual_utilities(),
            attribute_specs={...}
        )
        
        sums = importance.sum(axis=1)
        np.testing.assert_allclose(sums, 1.0, atol=0.01)

class TestMarketSimulator:
    """市场模拟器单元测试"""
    
    def test_shares_sum_to_one(self, sample_utilities):
        """测试份额之和为100%"""
        sim = MarketSimulator(sample_utilities, attribute_specs={...})
        scenarios = [
            {"name": "A", "price": 2999, "brand": "huawei"},
            {"name": "B", "price": 3999, "brand": "xiaomi"}
        ]
        
        result = sim.simulate_share(scenarios, none_option=False)
        total = result["predicted_share"].sum()
        np.testing.assert_allclose(total, 1.0, atol=0.01)
    
    def test_lower_price_higher_share(self, sample_utilities):
        """测试低价产品份额更高"""
        # 控制其他变量，仅改变价格
        pass
```

---

## 十、推荐技术栈

```yaml
# 完整技术栈清单

编程语言: Python 3.10+

数据处理:
  - pandas       # 数据清洗与转换
  - numpy        # 数值计算
  - pyarrow      # Parquet 格式支持

统计建模:
  - PyMC >= 5.0      # 分层贝叶斯 MCMC 采样（核心）
  - arviz            # 贝叶斯诊断与可视化
  - scipy            # 统计分布与优化
  - statsmodels      # MNL 基线模型
  - scikit-learn     # 潜在类别聚类

选择模型专用:
  - choice-learn     # 现代选择模型库（支持 HB/MNL/LatentClass）
  - biogeme          # 经典离散选择模型（可选）

LLM集成:
  - langchain        # Agent 框架
  - langchain-openai # OpenAI 接口
  - openai           # API 调用

可视化:
  - matplotlib       # 静态图表
  - seaborn          # 统计可视化
  - plotly           # 交互式图表（可选）

报告生成:
  - markdown         # Markdown 报告
  - pypandoc         # 转换为 PDF/Word
  - jinja2           # 报告模板引擎

开发工具:
  - pytest           # 单元测试
  - black            # 代码格式化
  - ruff             # 代码检查
  - mypy             # 类型检查
```

### 10.1 依赖文件

```txt
# requirements.txt

# 核心依赖
pandas>=2.0.0
numpy>=1.24.0
pyarrow>=12.0.0

# 统计建模
pymc>=5.10.0
arviz>=0.17.0
scipy>=1.11.0
statsmodels>=0.14.0
scikit-learn>=1.3.0

# 选择模型
choice-learn>=0.1.0

# LLM 集成
langchain>=0.1.0
langchain-openai>=0.0.5
openai>=1.0.0

# 可视化
matplotlib>=3.7.0
seaborn>=0.12.0
plotly>=5.15.0

# 报告生成
pypandoc>=1.11
jinja2>=3.1.0

# 开发工具
pytest>=7.4.0
pytest-cov>=4.1.0
black>=23.7.0
ruff>=0.0.280
mypy>=1.5.0
```

---

## 十一、目录结构建议

```
cbc-analysis-system/
├── docs/                               # 文档目录
│   ├── 01-CBC数据分析系统架构.md        # 本文档
│   ├── 02-数据接口规范.md              # 与问卷系统的数据交换规范
│   ├── 03-模型实现指南.md              # 各模型的详细实现说明
│   ├── 04-LLM-Agent设计.md             # Agent 工具与 Prompt 设计
│   └── 05-测试与验证规范.md            # 基准测试与单元测试规范
│
├── src/                                # 源代码
│   ├── cbc_analysis/                   # 主包
│   │   ├── __init__.py
│   │   ├── data/                       # 数据接入层
│   │   │   ├── __init__.py
│   │   │   ├── loader.py               # 数据加载器
│   │   │   ├── validator.py            # 数据校验器
│   │   │   └── transformer.py          # 数据转换器（编码等）
│   │   │
│   │   ├── models/                     # 建模引擎层
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # 基类定义
│   │   │   ├── mnl.py                  # MNL 模型
│   │   │   ├── hb.py                   # HB 模型
│   │   │   ├── latent_class.py         # 潜在类别模型
│   │   │   └── mixed_logit.py          # Mixed Logit 模型
│   │   │
│   │   ├── results/                    # 结果处理层
│   │   │   ├── __init__.py
│   │   │   ├── importance.py           # 重要性计算
│   │   │   ├── wtp.py                  # WTP 计算
│   │   │   └── aggregator.py           # 结果聚合
│   │   │
│   │   ├── simulation/                 # 市场模拟层
│   │   │   ├── __init__.py
│   │   │   ├── simulator.py            # 市场份额模拟
│   │   │   └── scenario.py             # 情景管理
│   │   │
│   │   ├── agent/                      # LLM Agent 层
│   │   │   ├── __init__.py
│   │   │   ├── tools.py                # Agent 工具定义
│   │   │   ├── prompts.py              # Prompt 模板
│   │   │   └── interpreter.py          # 结果解读器
│   │   │
│   │   ├── visualization/              # 可视化层
│   │   │   ├── __init__.py
│   │   │   ├── importance_plots.py
│   │   │   ├── utility_plots.py
│   │   │   ├── market_sim_plots.py
│   │   │   └── diagnostics_plots.py
│   │   │
│   │   └── reporting/                  # 报告生成层
│   │       ├── __init__.py
│   │       ├── builder.py              # 报告构建器
│   │       └── templates/              # 报告模板
│   │           ├── default.md.j2
│   │           └── executive.md.j2
│   │
│   └── cli.py                          # 命令行入口
│
├── tests/                              # 测试目录
│   ├── conftest.py                     # pytest 配置
│   ├── test_data/                      # 测试数据
│   │   ├── synthetic_cbc.csv
│   │   └── sawtooth_benchmark.csv      # Sawtooth 基准数据
│   ├── unit/                           # 单元测试
│   │   ├── test_loader.py
│   │   ├── test_mnl.py
│   │   ├── test_hb.py
│   │   ├── test_importance.py
│   │   └── test_simulator.py
│   └── integration/                    # 集成测试
│       └── test_full_pipeline.py       # 端到端流程测试
│
├── notebooks/                          # 示例 Notebook
│   ├── 01-快速开始.ipynb
│   ├── 02-HB模型详解.ipynb
│   ├── 03-市场模拟示例.ipynb
│   └── 04-LLM-Agent交互.ipynb
│
├── examples/                           # 示例代码
│   ├── basic_analysis.py               # 基础分析流程
│   ├── advanced_hb.py                  # 高级 HB 建模
│   └── market_simulation.py            # 市场模拟
│
├── pyproject.toml                      # 项目配置
├── requirements.txt                    # 依赖列表
└── README.md                           # 项目说明
```

---

## 十二、关键难点与应对策略

| 难点 | 应对策略 | 实现方式 |
|------|---------|---------|
| **统计模型编码复杂** | 提供经过验证的模板，LLM 根据项目需求定制参数 | `ModelTemplateLibrary` 类封装各模型的标准模板 |
| **MCMC 收敛诊断** | 自动生成收敛图与统计量，LLM 解释诊断结果 | `convergence_diagnostics()` + LLM 解读 Prompt |
| **错误数据/格式问题** | 解析错误日志，建议修复方案 | `DataValidator` 预检查 + LLM 错误诊断 |
| **用户统计知识不足** | 用通俗语言解释模型原理与结果 | `ResultInterpreter` 将统计术语翻译为业务语言 |
| **编码方案混淆** | 自动检测属性类型，选择正确编码 | `EncodingSelector` 根据 `metadata.attributes` 自动配置 |
| **WTP 计算异常** | 检测价格系数符号，过滤极端值 | `WTPCalculator` 内置异常值检测 |
| **市场份额预测失真** | 校准 "都不选" 选项的效用基准 | `MarketSimulator` 支持外部分部基准校准 |

---

## 十三、开发优先级建议

| 阶段 | 模块 | 优先级 | 说明 |
|------|------|--------|------|
| **Phase 1** | 数据接入层 | P0 | 基础，所有分析的前提 |
| **Phase 1** | MNL 基线模型 | P0 | 快速实现，验证数据流 |
| **Phase 1** | 重要性/WTP 计算 | P0 | 核心输出指标 |
| **Phase 2** | HB 核心模型 | P0 | 最重要的统计模型 |
| **Phase 2** | 收敛诊断 | P1 | 保障 HB 结果可靠性 |
| **Phase 2** | 市场模拟器 | P1 | 业务价值高 |
| **Phase 3** | LLM Agent | P1 | 差异化能力 |
| **Phase 3** | 自动报告生成 | P2 | 提升效率 |
| **Phase 3** | 潜在类别模型 | P2 | 进阶分析 |
| **Phase 4** | 可视化优化 | P2 | 交互式图表 |
| **Phase 4** | PDF 导出 | P3 | 报告交付 |

---

*本文档与以下文件配套使用：*
- `cbc-questionnaire-system/01-CBC系统架构与解决方案.md`（问卷生成系统）
- `cbc-questionnaire-system/04-CBC与模拟消费者集成方案.md`（数据交换标准）
- `consumer-simulation/` 系列文档（消费者模拟系统）
