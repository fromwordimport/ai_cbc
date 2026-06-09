# CBC 数据分析系统 — LLM Agent 设计

> **版本**：v1.0  
> **定位**：定义 LLM 驱动的交互分析 Agent 的工具集、Prompt 模板与对话流程  
> **前置文档**：`01-CBC数据分析系统架构.md`、`03-模型实现指南.md`

---

## 一、Agent 架构设计

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                       用户输入层                                 │
│              （自然语言问题、命令、情景描述）                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       LLM 意图解析                               │
│  • 识别用户意图类型（查询/建模/模拟/报告）                        │
│  • 提取关键实体（属性名、模型类型、情景参数）                      │
│  • 判断是否需要调用工具                                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       工具调用层                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ 数据工具  │  │ 建模工具  │  │ 计算工具  │  │ 可视化工具│        │
│  │          │  │          │  │          │  │          │        │
│  │load_data │  │fit_model │  │compute_  │  │plot_     │        │
│  │get_summary│ │get_diagnostics│wtp    │  │importance│        │
│  │          │  │          │  │simulate_ │  │          │        │
│  │          │  │          │  │market    │  │          │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       结果解读层                                 │
│  • 将统计输出翻译为业务语言                                      │
│  • 判断结果是否合理（异常检测）                                  │
│  • 生成可操作的建议                                              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       输出层                                     │
│  • 自然语言回复                                                  │
│  • 结构化数据（表格/JSON）                                       │
│  • 可视化图表                                                    │
│  • 完整报告（Markdown/PDF）                                      │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 状态管理

```python
from dataclasses import dataclass, field
from typing import Optional, Any
import pandas as pd

@dataclass
class AnalysisSession:
    """
    分析会话状态
    
    维护用户当前的分析上下文，支持多轮对话
    """
    session_id: str
    
    # 数据层
    data_loaded: bool = False
    data_path: Optional[str] = None
    data_summary: Optional[dict] = None
    
    # 模型层
    model_fitted: bool = False
    model_type: Optional[str] = None  # "mnl" / "hb" / "latent_class"
    model_results: Optional[Any] = None
    convergence_ok: Optional[bool] = None
    
    # 结果层
    utilities: Optional[pd.DataFrame] = None
    importance: Optional[pd.DataFrame] = None
    wtp: Optional[pd.DataFrame] = None
    
    # 模拟层
    last_simulation: Optional[pd.DataFrame] = None
    
    # 对话历史
    chat_history: list[dict] = field(default_factory=list)
    
    def to_context_string(self) -> str:
        """将会话状态转换为 LLM 上下文字符串"""
        parts = ["=== 当前分析状态 ==="]
        
        if self.data_loaded:
            parts.append(f"数据: {self.data_summary['n_respondents']} 受访者, "
                        f"{self.data_summary['n_choice_sets']} 选择集/人")
        
        if self.model_fitted:
            parts.append(f"模型: {self.model_type.upper()} 已拟合")
            if self.convergence_ok is not None:
                parts.append(f"收敛: {'✓' if self.convergence_ok else '✗'}")
        
        if self.importance is not None:
            top_attr = self.importance.sort_values("mean", ascending=False).index[0]
            parts.append(f"最重要属性: {top_attr}")
        
        return "\n".join(parts)
```

---

## 二、工具集设计

### 2.1 工具定义

```python
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

# ── 数据工具 ──

class LoadDataInput(BaseModel):
    file_path: str = Field(description="数据文件路径（JSON/CSV/Parquet）")
    encoding_scheme: str = Field(default="effects", description="编码方案")

class LoadDataTool:
    """加载 CBC 数据"""
    
    name = "load_data"
    description = "加载 CBC 数据文件。输入：文件路径。返回数据摘要。"
    args_schema = LoadDataInput
    
    def _run(self, file_path: str, encoding_scheme: str = "effects") -> str:
        try:
            loader = CBCDatasetLoader()
            loader.load(file_path)
            summary = loader.get_summary()
            
            # 更新会话状态
            session.data_loaded = True
            session.data_path = file_path
            session.data_summary = summary
            
            return (
                f"数据加载成功！\n"
                f"- 受访者数: {summary['n_respondents']}\n"
                f"- 选择集数/人: {summary['n_choice_sets']}\n"
                f"- 总记录数: {summary['n_records']}\n"
                f"- 属性数: {summary['n_attributes']}"
            )
        except Exception as e:
            return f"数据加载失败: {str(e)}"

# ── 建模工具 ──

class FitModelInput(BaseModel):
    model_type: str = Field(description="模型类型：mnl / hb / latent_class")
    n_draws: int = Field(default=1000, description="HB 模型的采样次数")
    n_chains: int = Field(default=4, description="HB 模型的并行链数")

class FitModelTool:
    """拟合统计模型"""
    
    name = "fit_model"
    description = "拟合 CBC 分析模型。输入：模型类型（mnl/hb/latent_class）。返回拟合结果摘要。"
    args_schema = FitModelInput
    
    def _run(self, model_type: str, n_draws: int = 1000, n_chains: int = 4) -> str:
        if not session.data_loaded:
            return "请先加载数据（使用 load_data 工具）"
        
        try:
            data = loader.to_long_format()
            feature_cols = loader.get_encoded_cols()
            
            if model_type.lower() == "mnl":
                model = MNLModel(data, feature_cols)
                model.fit()
                fit = model.get_model_fit()
                
                session.model_fitted = True
                session.model_type = "mnl"
                session.model_results = model
                session.convergence_ok = fit["converged"]
                
                return (
                    f"MNL 模型拟合完成！\n"
                    f"- Log-Likelihood: {fit['log_likelihood']:.2f}\n"
                    f"- McFadden R²: {fit['mc_fadden_r2']:.4f}\n"
                    f"- AIC: {fit['aic']:.2f}\n"
                    f"- 收敛: {'✓' if fit['converged'] else '✗'}"
                )
            
            elif model_type.lower() == "hb":
                model = HBModel(data, feature_cols)
                model.build_model()
                trace = model.fit(n_draws=n_draws, n_chains=n_chains)
                diagnostics = model.convergence_diagnostics()
                
                session.model_fitted = True
                session.model_type = "hb"
                session.model_results = model
                session.convergence_ok = diagnostics["converged"]
                session.utilities = model.get_individual_utilities()
                
                return (
                    f"HB 模型拟合完成！\n"
                    f"- 采样: {n_chains} 链 × {n_draws} 次\n"
                    f"- R-hat (max): {diagnostics['rhat_max']:.4f}\n"
                    f"- ESS (min): {diagnostics['ess_bulk_min']:.0f}\n"
                    f"- 收敛: {'✓' if diagnostics['converged'] else '✗'}"
                )
            
            else:
                return f"不支持的模型类型: {model_type}"
        
        except Exception as e:
            return f"模型拟合失败: {str(e)}"

# ── 结果查询工具 ──

class GetCoefficientsTool:
    """获取模型系数"""
    
    name = "get_coefficients"
    description = "获取模型系数估计。输入：属性名（可选，不填返回全部）。"
    
    def _run(self, attribute: str = None) -> str:
        if not session.model_fitted:
            return "请先拟合模型"
        
        model = session.model_results
        
        if session.model_type == "mnl":
            coefs = model.get_coefficients()
            if attribute:
                coefs = coefs[coefs["parameter"].str.contains(attribute)]
            
            lines = ["=== 模型系数 ==="]
            for _, row in coefs.iterrows():
                sig = "***" if row["p_value"] < 0.001 else "**" if row["p_value"] < 0.01 else "*" if row["p_value"] < 0.05 else ""
                lines.append(
                    f"{row['parameter']}: {row['coef']:.4f} "
                    f"(SE={row['std_err']:.4f}, p={row['p_value']:.4f}) {sig}"
                )
            return "\n".join(lines)
        
        elif session.model_type == "hb":
            pop_params = model.get_population_parameters()
            lines = ["=== 总体参数后验摘要 ==="]
            lines.append(pop_params.to_string())
            return "\n".join(lines)

# ── 重要性工具 ──

class ComputeImportanceTool:
    """计算属性重要性"""
    
    name = "compute_importance"
    description = "计算各属性的相对重要性。无需参数。"
    
    def _run(self) -> str:
        if session.utilities is None:
            return "HB 模型未拟合，无法计算个体层面重要性"
        
        # 计算重要性
        importance = ImportanceCalculator.compute_importance(
            session.utilities,
            attribute_specs=loader.metadata["attributes"]
        )
        
        session.importance = importance
        
        # 聚合到群体层面
        summary = ResultAggregator.aggregate_results(importance)
        
        lines = ["=== 属性重要性 ==="]
        lines.append("| 排名 | 属性 | 重要性 | 标准差 | 95% CI |")
        lines.append("|------|------|--------|--------|--------|")
        
        summary_sorted = summary.sort_values("mean", ascending=False)
        for i, (attr, row) in enumerate(summary_sorted.iterrows(), 1):
            lines.append(
                f"| {i} | {attr} | {row['mean']:.1%} | {row['std']:.1%} | "
                f"[{row['ci_95_lower']:.1%}, {row['ci_95_upper']:.1%}] |"
            )
        
        return "\n".join(lines)

# ── WTP 工具 ──

class ComputeWTPTool:
    """计算支付意愿"""
    
    name = "compute_wtp"
    description = "计算属性的支付意愿。输入：属性名。"
    
    def _run(self, attribute: str) -> str:
        if session.utilities is None:
            return "请先拟合 HB 模型"
        
        calc = WTPCalculator(session.utilities)
        wtp = calc.compute_wtp(attribute)
        
        return (
            f"=== {attribute} 的支付意愿 ===\n"
            f"均值: ¥{wtp.mean():.0f}\n"
            f"中位数: ¥{wtp.median():.0f}\n"
            f"标准差: ¥{wtp.std():.0f}\n"
            f"95% CI: [¥{wtp.quantile(0.025):.0f}, ¥{wtp.quantile(0.975):.0f}]"
        )

# ── 市场模拟工具 ──

class SimulateMarketInput(BaseModel):
    scenarios_json: str = Field(description="竞争情景 JSON 数组")

class SimulateMarketTool:
    """模拟市场份额"""
    
    name = "simulate_market"
    description = """模拟市场份额。输入：JSON 格式的情景数组。
    示例：[{"name":"产品A","brand":"huawei","price":3999}]"""
    args_schema = SimulateMarketInput
    
    def _run(self, scenarios_json: str) -> str:
        if session.utilities is None:
            return "请先拟合 HB 模型"
        
        import json
        scenarios = json.loads(scenarios_json)
        
        sim = MarketSimulator(session.utilities, attribute_specs={...})
        result = sim.simulate_share(scenarios)
        
        lines = ["=== 市场份额预测 ==="]
        lines.append("| 产品 | 份额 | 区间 |")
        lines.append("|------|------|------|")
        
        for _, row in result.iterrows():
            lines.append(
                f"| {row['scenario']} | {row['predicted_share']:.1%} | "
                f"[{row['share_ci_lower']:.1%}, {row['share_ci_upper']:.1%}] |"
            )
        
        session.last_simulation = result
        return "\n".join(lines)

# ── Python 代码执行工具 ──

class RunPythonInput(BaseModel):
    code: str = Field(description="Python 代码字符串")

class RunPythonTool:
    """执行 Python 代码"""
    
    name = "run_python"
    description = "执行自定义 Python 代码。输入：代码字符串。用于高级分析。"
    args_schema = RunPythonInput
    
    def _run(self, code: str) -> str:
        import io
        import sys
        
        # 安全检查
        is_safe, warnings = CodeSafetyChecker.check_code(code)
        if not is_safe:
            return f"代码安全检查未通过: {warnings}"
        
        # 执行代码
        stdout = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout
        
        try:
            local_vars = {
                "session": session,
                "data": loader.df if loader else None,
                "model": session.model_results,
                "utilities": session.utilities,
                "pd": pd,
                "np": np
            }
            exec(code, {"__builtins__": __builtins__}, local_vars)
            return stdout.getvalue() or "代码执行成功"
        except Exception as e:
            return f"执行错误: {str(e)}"
        finally:
            sys.stdout = old_stdout

# ── 报告生成工具 ──

class GenerateReportInput(BaseModel):
    report_type: str = Field(default="summary", description="报告类型：full/summary/market_sim")

class GenerateReportTool:
    """生成分析报告"""
    
    name = "generate_report"
    description = "生成分析报告。输入：报告类型（full/summary/market_sim）。"
    args_schema = GenerateReportInput
    
    def _run(self, report_type: str = "summary") -> str:
        builder = ReportBuilder()
        
        if report_type == "summary":
            report = builder.build_summary(
                data_summary=session.data_summary,
                model_results=session.model_results,
                importance=session.importance,
                wtp=session.wtp
            )
        elif report_type == "full":
            report = builder.build_full_report(...)
        
        # 保存报告
        output_path = f"/tmp/cbc_report_{report_type}.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        return f"报告已生成: {output_path}"
```

---

## 三、Prompt 模板设计

### 3.1 系统 Prompt

```markdown
# CBC 数据分析助手

你是一位专业的市场研究分析师，擅长联合分析（Conjoint Analysis）和离散选择模型。
你的任务是通过自然语言与用户交互，帮助他们分析 CBC 问卷数据。

## 核心能力

1. **数据加载与检查**：帮助用户加载 CBC 数据，检查数据质量
2. **统计建模**：拟合 MNL、HB 等模型，解释模型结果
3. **结果解读**：将统计输出翻译为业务语言
4. **市场模拟**：预测不同产品配置的市场份额
5. **报告生成**：生成结构化的分析报告

## 工作原则

- **准确性优先**：统计结果必须准确，不确定时明确说明
- **通俗解释**：用业务语言解释统计概念，避免过度术语化
- **主动建议**：根据数据特征主动建议合适的分析方法
- **异常检测**：发现数据或结果异常时及时提醒

## 可用工具

你可以使用以下工具来完成任务：

{tools_description}

## 当前状态

{session_state}

## 输出格式

- 使用 Markdown 格式输出
- 表格用于展示结构化数据
- 关键发现用 **粗体** 强调
- 异常结果用 ⚠️ 标记
```

### 3.2 意图识别 Prompt

```markdown
请分析用户的输入，判断其意图类型：

用户输入：{user_input}

可能的意图类型：
1. **数据操作** - 加载数据、查看数据摘要、检查数据质量
2. **建模** - 拟合模型、查看模型诊断、比较模型
3. **结果查询** - 查询系数、重要性、WTP
4. **市场模拟** - 预测市场份额、敏感度分析
5. **报告** - 生成报告、导出结果
6. **解释** - 解释统计概念、方法建议
7. **其他** - 无法归类的请求

请输出：
- intent_type: 意图类型
- entities: 提取的关键实体（属性名、模型类型、数值等）
- tool_needed: 是否需要调用工具，如果需要，列出工具名
- clarification_needed: 是否需要用户澄清（true/false）
- clarification_question: 如果需要澄清，提出具体问题
```

### 3.3 结果解读 Prompt

```markdown
请根据以下统计结果，生成业务解读：

## 分析背景
- 研究产品：{product_category}
- 样本量：{n_respondents} 位受访者
- 模型类型：{model_type}

## 统计结果
{statistical_results}

## 输出要求

1. **关键发现**（3-5条）：
   - 用业务语言描述最重要的发现
   - 包含具体数值和置信度
   - 指出意外的发现

2. **属性重要性解读**：
   - 解释为什么某些属性更重要
   - 与行业常识对比

3. **WTP 解读**（如适用）：
   - 支付意愿的合理范围
   - 与当前定价的关系

4. **建议**：
   - 基于结果的产品/定价建议
   - 需要进一步验证的问题

注意：
- 如果统计结果不显著（p > 0.05），明确指出
- 如果模型未收敛，建议增加迭代
- 避免过度解读
```

---

## 四、对话流程示例

### 4.1 完整分析对话

```markdown
> 用户：帮我分析一下 CBC 数据
> Agent：好的！请提供 CBC 数据文件的路径（支持 JSON、CSV、Parquet 格式）。
>       或者如果您已经导出了数据，请告诉我文件位置。

> 用户：文件在 data/cbc_results.json
> Agent：[调用 load_data("data/cbc_results.json")]
>       数据加载成功！
>       - 受访者数: 200
>       - 选择集数/人: 12
>       - 总记录数: 7200
>       - 属性数: 5（品牌、价格、存储、电池、充电）
>       
>       数据质量检查通过，样本量充足。
>       建议拟合 HB 模型以获得个体层面的效用估计。是否继续？

> 用户：拟合 HB 模型
> Agent：[调用 fit_model("hb", n_draws=1000, n_chains=4)]
>       HB 模型拟合完成！
>       - 采样: 4 链 × 1000 次
>       - R-hat (max): 1.03 ✓
>       - ESS (min): 482 ✓
>       - 收敛: ✓ 已收敛
>       
>       模型收敛良好，结果可靠。接下来可以：
>       1. 查看属性重要性
>       2. 计算支付意愿
>       3. 进行市场模拟

> 用户：查看属性重要性
> Agent：[调用 compute_importance()]
>       === 属性重要性 ===
>       | 排名 | 属性   | 重要性 | 标准差 | 95% CI       |
>       |------|--------|--------|--------|--------------|
>       | 1    | 价格   | 45.2%  | 8.3%   | [38%, 52%]   |
>       | 2    | 品牌   | 23.8%  | 5.1%   | [19%, 29%]   |
>       | 3    | 充电   | 15.3%  | 4.2%   | [12%, 20%]   |
>       | 4    | 存储   | 11.2%  | 3.8%   | [8%, 15%]    |
>       | 5    | 电池   | 4.5%   | 2.1%   | [3%, 6%]     |
>       
>       **关键发现**：
>       - 价格是最重要的决策因素（45.2%），显著高于其他属性
>       - 品牌和充电功率合计占比近 40%，说明消费者关注综合体验
>       - 电池容量的重要性最低（4.5%），可能因为当前产品已满足基本需求

> 用户：计算各属性的支付意愿
> Agent：[调用 compute_wtp("storage"), compute_wtp("charging")]
>       === 支付意愿汇总 ===
>       | 属性对比          | WTP 均值 | 中位数 | 95% CI        |
>       |-------------------|----------|--------|---------------|
>       | 256GB vs 128GB    | ¥420     | ¥380   | [¥180, ¥680]  |
>       | 512GB vs 128GB    | ¥680     | ¥620   | [¥320, ¥1020] |
>       | 120W vs 33W       | ¥580     | ¥520   | [¥250, ¥920]  |
>       | 华为 vs 小米      | ¥380     | ¥350   | [¥120, ¥650]  |
>       
>       **洞察**：
>       - 消费者愿意为 256GB 存储升级支付约 ¥420
>       - 快充（120W vs 33W）的溢价空间约为 ¥580
>       - 华为品牌溢价约为 ¥380，低于快充升级的价值

> 用户：如果我推出一款 2999 元的华为 256GB 手机，和小米 3999 元 512GB、
>      苹果 4999 元 256GB 竞争，份额多少？
> Agent：[调用 simulate_market(...)]
>       === 市场份额预测 ===
>       | 产品           | 份额   | 95% CI      |
>       |----------------|--------|-------------|
>       | 华为 256GB     | 38.5%  | [34%, 43%]  |
>       | 小米 512GB     | 31.2%  | [27%, 35%]  |
>       | 苹果 256GB     | 22.8%  | [19%, 27%]  |
>       | 都不选         | 7.5%   | [5%, 10%]   |
>       
>       **竞争分析**：
003e       - 你的产品预计获得最高份额（38.5%），价格优势明显
>       - 小米凭借大存储（512GB）获得 31.2%，存储升级党是你的主要对手
>       - 苹果品牌溢价支撑 22.8% 份额，但价格敏感消费者会流失
>       - 建议：考虑在 2999 价位提供差异化配置（如快充）以巩固优势

> 用户：生成完整报告
> Agent：[调用 generate_report("full")]
>       完整分析报告已生成！
>       📄 报告位置: /tmp/cbc_report_full.md
>       >       报告包含：
>       - 数据概况与质量评估
>       - HB 模型诊断
>       - 属性重要性与部分效用值
>       - 支付意愿分析
>       - 市场模拟结果
>       - 业务建议
```

---

## 五、异常处理 Prompt

### 5.1 模型未收敛

```markdown
模型未收敛（R-hat = {rhat} > 1.1）。可能原因：

1. 预烧期不足 → 建议增加 n_tune 到 2000
2. 先验设定不合理 → 检查先验是否与数据尺度匹配
3. 属性过多 → 尝试减少属性或合并水平
4. 数据质量问题 → 检查是否有完全分离

建议操作：增加采样迭代后重新拟合，或改用 MNL 模型作为基线。
```

### 5.2 价格系数为正

```markdown
⚠️ 检测到价格系数为正值（{price_coef}），这与经济学直觉不符。

可能原因：
- 属性编码错误（价格应使用连续编码）
- 样本量过小，估计不稳定
- 属性间存在多重共线性

建议：
1. 检查数据中的价格编码方式
2. 如果编码正确，增加样本量或使用更强先验
3. 当前结果应谨慎解读
```

---

## 六、API 设计

### 6.1 Agent 接口

```python
class CBCAnalysisAgent:
    """CBC 分析 Agent"""
    
    def __init__(self, llm: BaseLanguageModel):
        self.llm = llm
        self.session = AnalysisSession(session_id=str(uuid.uuid4()))
        self.tools = self._build_tools()
        self.agent = self._build_agent()
    
    def chat(self, message: str) -> str:
        """
        处理用户消息
        
        Parameters
        ----------
        message : str
            用户输入
        
        Returns
        -------
        str : Agent 回复
        """
        # 更新对话历史
        self.session.chat_history.append({"role": "user", "content": message})
        
        # 构建上下文
        context = self.session.to_context_string()
        
        # 调用 Agent
        response = self.agent.run(
            input=message,
            chat_history=self.session.chat_history,
            session_context=context
        )
        
        # 更新对话历史
        self.session.chat_history.append({"role": "assistant", "content": response})
        
        return response
    
    def export_session(self) -> dict:
        """导出会话状态（用于持久化）"""
        return {
            "session_id": self.session.session_id,
            "data_loaded": self.session.data_loaded,
            "model_fitted": self.session.model_fitted,
            "model_type": self.session.model_type,
            "chat_history": self.session.chat_history
        }
```

### 6.2 流式输出

```python
async def chat_stream(self, message: str):
    """流式输出回复"""
    # 用于 Web 界面，逐步返回内容
    async for chunk in self.agent.astream({"input": message}):
        yield chunk
```

---

## 七、安全设计

### 7.1 代码执行沙盒

```python
class SandboxExecutor:
    """沙盒代码执行器"""
    
    ALLOWED_MODULES = {
        "pandas", "numpy", "scipy", "matplotlib", "seaborn",
        "sklearn", "pymc", "arviz", "statsmodels"
    }
    
    FORBIDDEN_PATTERNS = [
        "os.system", "subprocess", "eval(", "exec(",
        "__import__", "importlib", "open(", ".write(", ".delete("
    ]
    
    @classmethod
    def execute(cls, code: str, timeout: int = 30) -> dict:
        """在沙盒中执行代码"""
        # 安全检查
        for pattern in cls.FORBIDDEN_PATTERNS:
            if pattern in code:
                return {"error": f"检测到禁止操作: {pattern}"}
        
        # 超时执行
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("代码执行超时")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)
        
        try:
            # 创建受限命名空间
            safe_globals = {"__builtins__": {
                name: __builtins__[name]
                for name in ["abs", "all", "any", "dict", "float", "int", "len",
                           "list", "max", "min", "print", "range", "round", "str",
                           "sum", "tuple", "zip", "enumerate", "map", "filter"]
            }}
            
            exec(code, safe_globals, {})
            signal.alarm(0)
            
            return {"output": "执行成功"}
        except TimeoutError:
            return {"error": "代码执行超时（30秒）"}
        except Exception as e:
            return {"error": str(e)}
```

### 7.2 结果校验

```python
class ResultValidator:
    """结果校验器"""
    
    @staticmethod
    def validate_importance(importance: pd.DataFrame) -> list[str]:
        """校验重要性结果"""
        warnings = []
        
        # 检查是否和为1
        sums = importance.sum(axis=1)
        if not np.allclose(sums, 1.0, atol=0.01):
            warnings.append("属性重要性之和不等于 100%")
        
        # 检查是否有负值
        if (importance < 0).any().any():
            warnings.append("存在负的重要性值")
        
        # 检查是否有极大值
        if (importance > 0.8).any().any():
            warnings.append("某属性重要性超过 80%，可能过度主导")
        
        return warnings
    
    @staticmethod
    def validate_shares(shares: pd.DataFrame) -> list[str]:
        """校验份额结果"""
        warnings = []
        
        total = shares["predicted_share"].sum()
        if not np.isclose(total, 1.0, atol=0.01):
            warnings.append(f"份额之和为 {total:.1%}，不等于 100%")
        
        if (shares["predicted_share"] < 0).any():
            warnings.append("存在负的份额预测")
        
        return warnings
```

---

*本文档与以下文件配套使用：*
- `01-CBC数据分析系统架构.md`（整体架构）
- `03-模型实现指南.md`（模型实现细节）
- `05-测试与验证规范.md`（测试策略）
