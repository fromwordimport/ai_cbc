# 建模管线与API设计

> **版本**：v1.0
> **定位**：定义联合分析统计建模的技术实现方案、API接口与数据管道
> **负责人**：小数（数据/建模科学家）+ 小端（后端/工具集成工程师）
> **核心目标**：让Agent能够通过标准接口调用建模工具，实现端到端自动化

---

## 一、总体架构

### 1.1 建模管线数据流

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        建模管线数据流                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  输入：CBC问卷回答数据（标准交换格式）                                        │
│    │                                                                        │
│    ▼                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  1. 数据预处理层（Data Preprocessor）                                │   │
│  │     • Schema校验 → 长格式转换 → 编码处理 → 缺失值处理               │   │
│  │     • 输出：analysis_ready.parquet                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│    │                                                                        │
│    ▼                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  2. 模型拟合层（Model Fitter）                                       │   │
│  │     • 自动模型选择 → MNL基线 → HB核心 → 收敛诊断                     │   │
│  │     • 输出：fitted_model.pkl + convergence_report.json               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│    │                                                                        │
│    ▼                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  3. 结果计算层（Result Calculator）                                  │   │
│  │     • 效用提取 → 重要性计算 → WTP计算 → 置信区间                     │   │
│  │     • 输出：results.json                                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│    │                                                                        │
│    ▼                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  4. 市场模拟层（Market Simulator）                                   │   │
│  │     • 竞争情景定义 → 份额预测 → 敏感度分析                           │   │
│  │     • 输出：simulation_results.json                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│    │                                                                        │
│    ▼                                                                        │
│  输出：分析报告 + 可视化图表 + 原始数据                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、数据预处理层

### 2.1 输入数据规范

```json
{
  "metadata": {
    "study_id": "dishwasher-202506",
    "n_respondents": 150,
    "n_choice_sets": 12,
    "n_alternatives": 3,
    "attributes": [
      {"id": "price", "name": "价格", "type": "price", "levels": [2999, 3999, 4999, 5999]},
      {"id": "capacity", "name": "容量", "type": "categorical", "levels": ["6套", "10套", "13套"]},
      {"id": "installation", "name": "安装方式", "type": "categorical", "levels": ["台式", "嵌入式", "水槽式"]},
      {"id": "features", "name": "核心功能", "type": "categorical", "levels": ["基础", "智能", "全能"]},
      {"id": "brand", "name": "品牌", "type": "categorical", "levels": ["美的", "西门子", "方太", "小米"]},
      {"id": "energy", "name": "能耗等级", "type": "categorical", "levels": ["二级", "一级", "超一级"]}
    ]
  },
  "choice_records": [
    {
      "respondent_id": "persona-001",
      "respondent_index": 0,
      "segment": "精致白领",
      "choice_set_id": 1,
      "choice_set_index": 0,
      "alternatives": [
        {"alt_index": 0, "chosen": false, "attributes": {"price": 3999, "capacity": "6套", "installation": "台式", "features": "智能", "brand": "小米", "energy": "一级"}},
        {"alt_index": 1, "chosen": true, "attributes": {"price": 4999, "capacity": "10套", "installation": "嵌入式", "features": "全能", "brand": "方太", "energy": "超一级"}},
        {"alt_index": 2, "chosen": false, "attributes": {"price": 2999, "capacity": "6套", "installation": "台式", "features": "基础", "brand": "美的", "energy": "二级"}}
      ],
      "none_chosen": false
    }
  ]
}
```

### 2.2 长格式转换

```python
class DataPreprocessor:
    """数据预处理引擎"""
    
    def to_long_format(self, raw_data: dict) -> pd.DataFrame:
        """
        将标准交换格式转换为长格式（每行一个选项）
        
        输出列：
        - resp_id: 受访者ID
        - resp_index: 受访者索引
        - task_id: 选择集ID
        - task_index: 选择集索引
        - alt_id: 选项索引
        - chosen: 是否被选中 (0/1)
        - price: 价格（连续）
        - capacity_6: 容量6套编码
        - capacity_10: 容量10套编码
        - ... (其他编码属性)
        """
        rows = []
        
        for record in raw_data["choice_records"]:
            for alt in record["alternatives"]:
                row = {
                    "resp_id": record["respondent_id"],
                    "resp_index": record["respondent_index"],
                    "task_id": record["choice_set_id"],
                    "task_index": record["choice_set_index"],
                    "alt_id": alt["alt_index"],
                    "chosen": 1 if alt["chosen"] else 0,
                }
                
                # 编码属性值
                encoded = self._encode_attributes(
                    alt["attributes"],
                    raw_data["metadata"]["attributes"]
                )
                row.update(encoded)
                
                rows.append(row)
        
        return pd.DataFrame(rows)
    
    def _encode_attributes(self, attributes: dict, attr_specs: list) -> dict:
        """Effects Coding编码"""
        encoded = {}
        
        for spec in attr_specs:
            attr_id = spec["id"]
            value = attributes[attr_id]
            
            if spec["type"] == "price":
                # 价格作为连续变量
                encoded[attr_id] = value
                
            elif spec["type"] == "categorical":
                # Effects Coding
                levels = spec["levels"]
                n_levels = len(levels)
                idx = levels.index(value)
                
                # 生成 n-1 个编码变量
                for i in range(n_levels - 1):
                    col_name = f"{attr_id}_{i}"
                    if idx == i:
                        encoded[col_name] = 1
                    elif idx == n_levels - 1:
                        encoded[col_name] = -1
                    else:
                        encoded[col_name] = 0
        
        return encoded
```

### 2.3 数据校验规则

```python
VALIDATION_RULES = [
    {
        "name": "属性定义完整性",
        "check": "metadata.attributes 非空",
        "severity": "ERROR",
        "action": "拒绝分析"
    },
    {
        "name": "每题必有一选",
        "check": "每个choice_set中恰好一个chosen=1",
        "severity": "ERROR",
        "action": "标记异常记录"
    },
    {
        "name": "样本量充足性",
        "check": "n_respondents * n_choice_sets >= n_params * 5",
        "severity": "WARNING",
        "action": "提示精度可能不足"
    },
    {
        "name": "属性水平覆盖",
        "check": "每个水平至少出现10%",
        "severity": "WARNING",
        "action": "提示某些水平数据不足"
    },
    {
        "name": "价格系数方向预检",
        "check": "价格属性存在且为连续变量",
        "severity": "WARNING",
        "action": "提醒无法计算WTP"
    }
]
```

---

## 三、模型拟合层

### 3.1 自动模型选择策略

```
输入数据特征
   │
   ├── 样本量 >= 100 且 属性数 <= 6？
   │   ├── 是 → HB (Hierarchical Bayes) 【推荐】
   │   │        • 个体层面效用估计
   │   │        • 多元正态异质性分布
   │   │        • 需要 MCMC 采样
   │   │
   │   └── 否 → 选择集数量 >= 12 每受访者？
   │            ├── 是 → Mixed Logit (MXL)
   │            │        • 随机参数Logit
   │            │        • 模拟积分估计
   │            │
   │            └── 否 → MNL (Multinomial Logit)
   │                     • 条件Logit基线
   │                     • 聚合层面估计
   │
   └── 需要人群细分？ → Latent Class Analysis (LCA)
```

### 3.2 HB模型实现（核心）

```python
class HBModel:
    """
    分层贝叶斯 Mixed Logit 模型
    使用 PyMC 实现
    """
    
    def __init__(self, data: pd.DataFrame, attribute_cols: list[str]):
        self.data = data
        self.attribute_cols = attribute_cols
        self.resp_ids = data["resp_id"].unique()
        self.n_resp = len(self.resp_ids)
        self.n_attrs = len(attribute_cols)
        
        # 预处理
        self._preprocess()
    
    def _preprocess(self):
        """构建模型所需的数据结构"""
        self.data["resp_idx"] = self.data["resp_id"].map(
            {rid: i for i, rid in enumerate(self.resp_ids)}
        )
        
        # 按选择集分组
        self.task_groups = self.data.groupby(["resp_id", "task_id"])
        self.n_tasks = len(self.task_groups)
        
        # 预计算每个任务的属性矩阵和选择结果
        self.task_data = []
        for (resp, task), group in self.task_groups:
            self.task_data.append({
                "X": group[self.attribute_cols].values,
                "y": group[group["chosen"] == 1].index[0] - group.index[0],
                "resp_idx": self.resp_ids.tolist().index(resp)
            })
    
    def build_model(self, prior_config: dict = None):
        """构建 PyMC 模型"""
        if prior_config is None:
            prior_config = {
                "mu_mu": 0,
                "mu_sigma": 10,
            }
        
        self.model = pm.Model()
        
        with self.model:
            # 总体超参数
            mu = pm.Normal("mu", mu=prior_config["mu_mu"], sigma=prior_config["mu_sigma"], shape=self.n_attrs)
            sigma = pm.HalfNormal("sigma", sigma=2, shape=self.n_attrs)
            
            # LKJ先验（相关性）
            chol, corr, stds = pm.LKJCholeskyCov(
                "chol", n=self.n_attrs, eta=2.0,
                sd_dist=pm.Exponential.dist(1.0, shape=self.n_attrs)
            )
            
            # 个体系数（非中心化参数化）
            z = pm.Normal("z", mu=0, sigma=1, shape=(self.n_resp, self.n_attrs))
            beta = pm.Deterministic("beta", mu + (chol @ z.T).T)
            
            # 似然函数
            log_probs = []
            for task in self.task_data:
                utilities = pm.math.dot(task["X"], beta[task["resp_idx"]])
                log_prob = pm.math.log_softmax(utilities)[task["y"]]
                log_probs.append(log_prob)
            
            pm.Potential("log_likelihood", pm.math.sum(log_probs))
    
    def fit(self, n_draws: int = 1000, n_tune: int = 1000, n_chains: int = 4):
        """运行 MCMC 采样"""
        with self.model:
            self.trace = pm.sample(
                draws=n_draws, tune=n_tune, chains=n_chains,
                target_accept=0.9, return_inferencedata=True
            )
        return self.trace
    
    def convergence_diagnostics(self) -> dict:
        """收敛诊断"""
        import arviz as az
        
        rhat = az.rhat(self.trace, var_names=["mu", "sigma", "beta"])
        ess = az.ess(self.trace, var_names=["mu", "sigma", "beta"])
        
        return {
            "rhat_max": float(rhat.max().values),
            "ess_min": float(ess.min().values),
            "converged": float(rhat.max().values) < 1.1
        }
    
    def get_individual_utilities(self) -> pd.DataFrame:
        """提取个体层面的效用估计（后验均值）"""
        beta_posterior = self.trace.posterior["beta"]
        beta_mean = beta_posterior.mean(dim=["chain", "draw"]).values
        
        return pd.DataFrame(
            beta_mean, index=self.resp_ids, columns=self.attribute_cols
        )
```

### 3.3 API接口设计

```python
# 建模服务API（FastAPI）

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class FitRequest(BaseModel):
    """模型拟合请求"""
    study_id: str
    model_type: str = "hb"  # mnl, hb, latent_class
    data: dict  # 标准交换格式
    n_draws: int = 1000
    n_tune: int = 1000
    n_chains: int = 4

class FitResponse(BaseModel):
    """模型拟合响应"""
    job_id: str
    status: str  # PENDING, RUNNING, COMPLETED, FAILED
    model_type: str
    convergence: dict
    individual_utilities: dict  # resp_id -> {attribute: value}
    population_params: dict  # mu, sigma
    processing_time_seconds: float

@app.post("/api/v1/studies/{study_id}/analyze", response_model=FitResponse)
async def fit_model(request: FitRequest):
    """
    拟合统计模型
    
    流程：
    1. 接收标准交换数据
    2. 预处理（长格式转换、编码）
    3. 拟合指定模型
    4. 收敛诊断
    5. 返回结果
    """
    # 异步执行（后台任务）
    job_id = create_job(request)
    
    # 实际实现中，这里会触发后台任务
    # 此处返回 job_id，客户端可轮询状态
    
    return FitResponse(
        job_id=job_id,
        status="PENDING",
        model_type=request.model_type
    )

@app.get("/api/v1/studies/{study_id}/results")
async def get_results(study_id: str):
    """获取模型拟合结果"""
    job = get_job(study_id)
    
    if job.status == "COMPLETED":
        return {
            "status": "COMPLETED",
            "convergence": job.convergence,
            "individual_utilities": job.individual_utilities,
            "population_params": job.population_params,
            "importance": job.importance,
            "wtp": job.wtp
        }
    else:
        return {"status": job.status}
```

---

## 四、结果计算层

### 4.1 属性重要性计算

```python
class ImportanceCalculator:
    """属性重要性计算器"""
    
    @staticmethod
    def compute_importance(individual_utilities: pd.DataFrame, attribute_specs: dict) -> pd.DataFrame:
        """
        计算每个受访者的属性重要性
        
        公式：属性重要性 = 该属性各水平效用的极差 / 所有属性极差之和
        """
        importance_by_resp = []
        
        for resp_id, util_row in individual_utilities.iterrows():
            attr_ranges = {}
            
            for attr_name, spec in attribute_specs.items():
                if spec["type"] == "categorical":
                    # 从编码参数恢复各水平效用
                    level_utils = ImportanceCalculator._recover_level_utilities(util_row, attr_name, spec)
                    attr_ranges[attr_name] = level_utils.max() - level_utils.min()
                
                elif spec["type"] in ["continuous", "price"]:
                    # 连续变量：使用参数绝对值 × 属性范围
                    param = util_row.get(attr_name, 0)
                    attr_range = spec.get("range", [spec["levels"][0], spec["levels"][-1]])
                    attr_ranges[attr_name] = abs(param) * (attr_range[1] - attr_range[0])
            
            # 归一化
            total_range = sum(attr_ranges.values())
            importance = {k: v / total_range for k, v in attr_ranges.items()} if total_range > 0 else attr_ranges
            
            importance_by_resp.append(importance)
        
        return pd.DataFrame(importance_by_resp, index=individual_utilities.index)
    
    @staticmethod
    def _recover_level_utilities(util_row: pd.Series, attr_name: str, spec: dict) -> np.ndarray:
        """从effects coding参数恢复各水平效用值"""
        n_levels = len(spec["levels"])
        params = []
        
        for i in range(n_levels - 1):
            param_name = f"{attr_name}_{i}"
            params.append(util_row.get(param_name, 0))
        
        # 恢复最后一个水平
        params.append(-sum(params))
        
        return np.array(params)
```

### 4.2 WTP计算

```python
class WTPCalculator:
    """支付意愿计算器"""
    
    def __init__(self, individual_utilities: pd.DataFrame, price_col: str = "price"):
        self.util = individual_utilities
        self.price_col = price_col
        
        # 检查价格系数
        if price_col not in individual_utilities.columns:
            raise ValueError(f"价格列 '{price_col}' 不存在")
    
    def compute_wtp(self, feature_col: str, feature_type: str = "continuous") -> pd.Series:
        """
        计算某属性的支付意愿
        
        WTP = -beta_feature / beta_price
        """
        beta_price = self.util[self.price_col]
        beta_feature = self.util[feature_col]
        
        # 检查价格系数符号
        if (beta_price > 0).any():
            print("警告：部分受访者的价格系数为正")
        
        wtp = -beta_feature / beta_price
        
        # 过滤极端值
        wtp = wtp[np.abs(wtp) < wtp.quantile(0.99)]
        
        return wtp
```

---

## 五、Agent调用协议

### 5.1 工具调用接口

```python
# 分析Agent可用的工具集

ANALYSIS_TOOLS = {
    "fit_model": {
        "description": "拟合联合分析模型",
        "input": {"model_type": "hb|mnl|latent_class", "data": "标准交换格式"},
        "output": "模型结果对象",
        "async": True
    },
    
    "get_importance": {
        "description": "获取属性重要性",
        "input": {"model_results": "模型结果对象"},
        "output": "重要性数据框",
        "async": False
    },
    
    "compute_wtp": {
        "description": "计算支付意愿",
        "input": {"model_results": "模型结果对象", "attribute": "属性名"},
        "output": "WTP统计量",
        "async": False
    },
    
    "simulate_market": {
        "description": "模拟市场份额",
        "input": {"model_results": "模型结果对象", "scenarios": "竞争情景列表"},
        "output": "份额预测结果",
        "async": False
    },
    
    "segment_analysis": {
        "description": "按群体细分分析",
        "input": {"model_results": "模型结果对象", "segment_by": "分组维度"},
        "output": "细分结果",
        "async": False
    }
}
```

### 5.2 端到端调用示例

```python
# 分析Agent自动执行完整分析流程

class AnalysisPipeline:
    """分析管道 - Agent自动触发"""
    
    def run_full_analysis(self, study_id: str) -> AnalysisReport:
        """
        执行完整分析流程
        
        步骤：
        1. 加载数据
        2. 预处理
        3. 拟合HB模型
        4. 收敛诊断
        5. 计算重要性
        6. 计算WTP
        7. 市场模拟（默认情景）
        8. 细分分析
        9. 生成报告
        """
        
        # 1. 加载数据
        raw_data = self.load_data(study_id)
        
        # 2. 预处理
        preprocessor = DataPreprocessor()
        long_data = preprocessor.to_long_format(raw_data)
        
        # 3. 拟合模型
        model = HBModel(long_data, attribute_cols=[...])
        model.build_model()
        trace = model.fit()
        
        # 4. 收敛诊断
        diagnostics = model.convergence_diagnostics()
        if not diagnostics["converged"]:
            raise ModelConvergenceError("模型未收敛，需要增加采样次数")
        
        # 5. 提取效用
        individual_utilities = model.get_individual_utilities()
        
        # 6. 计算重要性
        importance = ImportanceCalculator.compute_importance(
            individual_utilities, raw_data["metadata"]["attributes"]
        )
        
        # 7. 计算WTP
        wtp_results = {}
        for attr in ["capacity", "installation", "features", "brand", "energy"]:
            wtp_results[attr] = WTPCalculator(individual_utilities).compute_wtp(attr)
        
        # 8. 市场模拟
        simulator = MarketSimulator(individual_utilities, raw_data["metadata"]["attributes"])
        default_scenarios = self._build_default_scenarios(raw_data)
        market_shares = simulator.simulate_share(default_scenarios)
        
        # 9. 细分分析
        segment_results = self._segment_analysis(individual_utilities, raw_data)
        
        # 10. 生成报告
        report = ReportBuilder().build(
            study_id=study_id,
            model_diagnostics=diagnostics,
            importance=importance,
            wtp=wtp_results,
            market_simulation=market_shares,
            segment_analysis=segment_results
        )
        
        return report
```

---

*本文档由小数和小端维护，API变更需双方确认。*
