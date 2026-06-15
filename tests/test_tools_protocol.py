"""Tests for the ToolCalling protocol.

Covers:
  1. Tool registration (sync + async)
  2. Tool invocation (sync + async)
  3. Argument validation
  4. Error handling
  5. Timeout management
  6. Retry logic
  7. Pipeline tools (PersonaProfile → CBCRawDataset → AnalysisResult)
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from aicbc.tools.protocol import (
    ToolCallError,
    ToolCallRequest,
    ToolCallResult,
    ToolCallStatus,
    ToolNotFoundError,
    ToolParameter,
    ToolRegistry,
    ToolSpec,
    ToolTimeoutError,
    ToolValidationError,
    _validate_arguments,
    call_tool,
    get_tool_spec,
    list_registered_tools,
    register_tool,
)

# Import pipeline tools to trigger their registration in the default registry
import aicbc.tools.pipeline  # noqa: F401


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> ToolRegistry:
    """Fresh tool registry for each test."""
    return ToolRegistry()


@pytest.fixture
def add_spec() -> ToolSpec:
    return ToolSpec(
        name="add",
        description="Add two numbers",
        parameters=[
            ToolParameter(name="a", type="integer", description="First number", required=True),
            ToolParameter(name="b", type="integer", description="Second number", required=True),
        ],
        timeout_seconds=1.0,
        max_retries=0,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_sync_tool(self, registry: ToolRegistry, add_spec: ToolSpec) -> None:
        def add(a: int, b: int) -> int:
            return a + b

        spec = registry.register(add, spec=add_spec)
        assert spec.name == "add"
        assert "add" in [s.name for s in registry.list_tools()]

    def test_register_async_tool(self, registry: ToolRegistry) -> None:
        async def async_greet(name: str) -> str:
            return f"Hello, {name}"

        spec = ToolSpec(
            name="async_greet",
            description="Greet someone",
            parameters=[ToolParameter(name="name", type="string", required=True)],
            timeout_seconds=1.0,
        )
        registry.register(async_greet, spec=spec)
        rt = registry._tools["async_greet"]
        assert rt.is_async is True

    def test_auto_derive_spec(self, registry: ToolRegistry) -> None:
        def multiply(x: int, y: int, factor: float = 1.0) -> float:
            return x * y * factor

        spec = registry.register(multiply)
        assert spec.name == "multiply"
        assert len(spec.parameters) == 3
        # Check that default param is not required
        factor_param = next(p for p in spec.parameters if p.name == "factor")
        assert factor_param.required is False

    def test_unregister(self, registry: ToolRegistry, add_spec: ToolSpec) -> None:
        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add, spec=add_spec)
        assert registry.unregister("add") is True
        assert registry.unregister("add") is False

    def test_get_spec_not_found(self, registry: ToolRegistry) -> None:
        with pytest.raises(ToolNotFoundError):
            registry.get_spec("nonexistent")


# ---------------------------------------------------------------------------
# Invocation (sync)
# ---------------------------------------------------------------------------


class TestSyncInvocation:
    def test_call_success(self, registry: ToolRegistry, add_spec: ToolSpec) -> None:
        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add, spec=add_spec)
        request = ToolCallRequest(tool_name="add", arguments={"a": 2, "b": 3})
        result = registry.call(request)

        assert result.is_success is True
        assert result.data == 5
        assert result.status == ToolCallStatus.SUCCESS
        assert result.duration_seconds >= 0

    def test_call_not_found(self, registry: ToolRegistry) -> None:
        request = ToolCallRequest(tool_name="missing", arguments={})
        result = registry.call(request)

        assert result.status == ToolCallStatus.NOT_FOUND
        assert result.is_success is False
        assert "not registered" in result.error

    def test_call_validation_error_missing_param(
        self, registry: ToolRegistry, add_spec: ToolSpec
    ) -> None:
        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add, spec=add_spec)
        request = ToolCallRequest(tool_name="add", arguments={"a": 2})
        result = registry.call(request)

        assert result.status == ToolCallStatus.VALIDATION_ERROR
        assert "Missing required parameter 'b'" in result.error

    def test_call_validation_error_unknown_param(
        self, registry: ToolRegistry, add_spec: ToolSpec
    ) -> None:
        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add, spec=add_spec)
        request = ToolCallRequest(tool_name="add", arguments={"a": 2, "b": 3, "c": 4})
        result = registry.call(request)

        assert result.status == ToolCallStatus.VALIDATION_ERROR
        assert "Unknown parameter 'c'" in result.error

    def test_call_with_timeout(self, registry: ToolRegistry) -> None:
        def slow_add(a: int, b: int) -> int:
            import time

            time.sleep(5)
            return a + b

        spec = ToolSpec(
            name="slow_add",
            description="Slow add",
            parameters=[
                ToolParameter(name="a", type="integer", required=True),
                ToolParameter(name="b", type="integer", required=True),
            ],
            timeout_seconds=0.1,
            max_retries=0,
        )
        registry.register(slow_add, spec=spec)
        request = ToolCallRequest(tool_name="slow_add", arguments={"a": 1, "b": 2})
        result = registry.call(request)

        assert result.status == ToolCallStatus.TIMEOUT
        assert "timed out" in result.error.lower()

    def test_call_with_retry(self, registry: ToolRegistry) -> None:
        call_count = 0

        def flaky_add(a: int, b: int) -> int:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Simulated connection failure")
            return a + b

        spec = ToolSpec(
            name="flaky_add",
            description="Flaky add",
            parameters=[
                ToolParameter(name="a", type="integer", required=True),
                ToolParameter(name="b", type="integer", required=True),
            ],
            timeout_seconds=1.0,
            max_retries=3,
            retryable_errors=(ConnectionError,),
        )
        registry.register(flaky_add, spec=spec)
        request = ToolCallRequest(tool_name="flaky_add", arguments={"a": 1, "b": 2})
        result = registry.call(request)

        assert result.is_success is True
        assert result.data == 3
        assert result.retry_count == 2  # 2 retries before success

    def test_call_non_retryable_error(self, registry: ToolRegistry) -> None:
        def bad_add(a: int, b: int) -> int:
            raise ValueError("Bad input")

        spec = ToolSpec(
            name="bad_add",
            description="Bad add",
            parameters=[
                ToolParameter(name="a", type="integer", required=True),
                ToolParameter(name="b", type="integer", required=True),
            ],
            timeout_seconds=1.0,
            max_retries=2,
            retryable_errors=(ConnectionError,),  # ValueError is NOT retryable
        )
        registry.register(bad_add, spec=spec)
        request = ToolCallRequest(tool_name="bad_add", arguments={"a": 1, "b": 2})
        result = registry.call(request)

        assert result.status == ToolCallStatus.ERROR
        assert "Bad input" in result.error
        assert result.retry_count == 0  # No retries attempted


# ---------------------------------------------------------------------------
# Invocation (async)
# ---------------------------------------------------------------------------


class TestAsyncInvocation:
    @pytest.mark.asyncio
    async def test_acall_success(self, registry: ToolRegistry) -> None:
        async def async_multiply(x: int, y: int) -> int:
            await asyncio.sleep(0.01)
            return x * y

        spec = ToolSpec(
            name="async_multiply",
            description="Async multiply",
            parameters=[
                ToolParameter(name="x", type="integer", required=True),
                ToolParameter(name="y", type="integer", required=True),
            ],
            timeout_seconds=1.0,
        )
        registry.register(async_multiply, spec=spec)
        request = ToolCallRequest(tool_name="async_multiply", arguments={"x": 3, "y": 4})
        result = await registry.acall(request)

        assert result.is_success is True
        assert result.data == 12

    @pytest.mark.asyncio
    async def test_acall_timeout(self, registry: ToolRegistry) -> None:
        async def slow_multiply(x: int, y: int) -> int:
            await asyncio.sleep(5)
            return x * y

        spec = ToolSpec(
            name="slow_multiply",
            description="Slow multiply",
            parameters=[
                ToolParameter(name="x", type="integer", required=True),
                ToolParameter(name="y", type="integer", required=True),
            ],
            timeout_seconds=0.1,
            max_retries=0,
        )
        registry.register(slow_multiply, spec=spec)
        request = ToolCallRequest(tool_name="slow_multiply", arguments={"x": 1, "y": 2})
        result = await registry.acall(request)

        assert result.status == ToolCallStatus.TIMEOUT


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


class TestArgumentValidation:
    def test_validate_required_params(self) -> None:
        spec = ToolSpec(
            name="test",
            description="Test",
            parameters=[
                ToolParameter(name="req", type="string", required=True),
                ToolParameter(name="opt", type="string", required=False, default="default_val"),
            ],
        )
        result = _validate_arguments(spec, {"req": "hello"})
        assert result["req"] == "hello"
        assert result["opt"] == "default_val"

    def test_validate_missing_required(self) -> None:
        spec = ToolSpec(
            name="test",
            description="Test",
            parameters=[ToolParameter(name="req", type="string", required=True)],
        )
        with pytest.raises(ToolValidationError) as exc_info:
            _validate_arguments(spec, {})
        assert "Missing required parameter" in str(exc_info.value)
        assert exc_info.value.param_name == "req"

    def test_validate_unknown_param(self) -> None:
        spec = ToolSpec(
            name="test",
            description="Test",
            parameters=[ToolParameter(name="known", type="string", required=True)],
        )
        with pytest.raises(ToolValidationError) as exc_info:
            _validate_arguments(spec, {"known": "x", "unknown": "y"})
        assert "Unknown parameter" in str(exc_info.value)
        assert exc_info.value.param_name == "unknown"


# ---------------------------------------------------------------------------
# OpenAI schema generation
# ---------------------------------------------------------------------------


class TestOpenAISchema:
    def test_to_openai_schema(self) -> None:
        spec = ToolSpec(
            name="search",
            description="Search documents",
            parameters=[
                ToolParameter(name="query", type="string", description="Search query", required=True),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Result limit",
                    required=False,
                    default=10,
                ),
            ],
        )
        schema = spec.to_openai_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "search"
        assert "query" in schema["function"]["parameters"]["properties"]
        assert "limit" in schema["function"]["parameters"]["properties"]
        assert schema["function"]["parameters"]["required"] == ["query"]


# ---------------------------------------------------------------------------
# Module-level convenience API
# ---------------------------------------------------------------------------


class TestConvenienceAPI:
    def test_register_tool_decorator(self) -> None:
        @register_tool(
            spec=ToolSpec(
                name="decorated_add",
                description="Decorated add",
                parameters=[
                    ToolParameter(name="a", type="integer", required=True),
                    ToolParameter(name="b", type="integer", required=True),
                ],
            )
        )
        def decorated_add(a: int, b: int) -> int:
            return a + b

        spec = get_tool_spec("decorated_add")
        assert spec.name == "decorated_add"

    def test_call_tool_convenience(self) -> None:
        @register_tool(
            spec=ToolSpec(
                name="convenience_multiply",
                description="Multiply",
                parameters=[
                    ToolParameter(name="x", type="integer", required=True),
                    ToolParameter(name="y", type="integer", required=True),
                ],
            )
        )
        def convenience_multiply(x: int, y: int) -> int:
            return x * y

        result = call_tool("convenience_multiply", x=5, y=6)
        assert result.is_success is True
        assert result.data == 30

    def test_list_registered_tools(self) -> None:
        tools = list_registered_tools()
        assert isinstance(tools, list)
        # Should include tools registered in previous tests + pipeline tools
        names = [t.name for t in tools]
        assert "convenience_multiply" in names


# ---------------------------------------------------------------------------
# Pipeline tools
# ---------------------------------------------------------------------------


class TestPipelineTools:
    def test_persona_to_questionnaire_context(self) -> None:
        """Test PersonaProfile → questionnaire context binding."""
        persona = {
            "persona_id": "persona-dw-001",
            "segment": "精致白领",
            "layer1_demographics": {
                "age": "28岁",
                "gender": "女",
                "city": "新一线城市",
                "income": "月收入15K-25K",
                "occupation": "互联网运营",
                "education": "本科",
                "marital_status": "已婚无孩",
                "living_type": "70㎡两居室，租房",
            },
            "layer2_behavior": {
                "price_sensitivity": "中高敏感",
                "purchase_channels": ["京东", "天猫"],
                "decision_style": "理性比较型",
                "brand_loyalty": "中等，重性价比",
                "information_source": ["小红书", "知乎"],
            },
            "layer3_psychology": {
                "core_values": ["效率", "品质生活"],
                "core_anxieties": ["时间不够用"],
                "tension_combination": {
                    "labels": ["追求品质", "精打细算"],
                    "narrative_explanation": "她渴望通过高品质产品提升生活体验，但受限于租房身份和中等收入，必须在每一笔消费中权衡性价比。",
                },
                "secret_motivation": "用科技产品证明自己的生活品味",
                "defense_mechanism": "合理化：说服自己这是长期投资",
            },
            "layer4_scenarios": {
                "daily_routine": "早9晚7，周末打扫",
                "purchase_trigger": "看到同事晒洗碗机，心动",
                "stress_response": "焦虑时更容易冲动消费",
                "social_behavior": "爱在社交媒体分享好物",
            },
            "dishwasher_context": {
                "purchase_constraints": ["厨房空间小", "租房不能大改"],
                "decision_factors": ["价格", "品牌口碑", "安装便捷性"],
                "ignored_factors": ["能耗等级", "智能功能"],
            },
            "language_samples": [
                "洗碗机真的是解放双手的神器，后悔没早买。",
                "租房也要讲究生活品质，小厨房也能装洗碗机。",
                "对比了三款，最后还是选了性价比最高的。",
            ],
            "authenticity_score": 11,
        }

        questionnaire = {
            "questionnaire_id": "q-dishwasher-202506",
            "study_id": "dishwasher-202506",
            "choice_sets": [],
            "design_parameters": {"n_choice_sets": 12, "n_alternatives": 3},
        }

        result = call_tool(
            "persona_to_questionnaire_context",
            persona=persona,
            questionnaire=questionnaire,
        )

        assert result.is_success is True
        ctx = result.data
        assert "persona_summary" in ctx
        assert "tension_narrative" in ctx
        assert "scenario_injection" in ctx
        assert "relevant_attributes" in ctx
        # Check attribute weighting
        rel_attrs = ctx["relevant_attributes"]
        assert rel_attrs.get("价格", 0) > rel_attrs.get("能耗等级", 0)

    def test_responses_to_raw_dataset(self) -> None:
        """Test PersonaResponse list → CBCRawDataset aggregation."""
        responses = [
            {
                "response_id": "resp-001",
                "study_id": "dishwasher-202506",
                "persona_id": "persona-dw-001",
                "questionnaire_id": "q-dishwasher-202506",
                "segment": "精致白领",
                "responses": [
                    {"choice_set_id": 1, "chosen_alt_index": 0, "reasoning": "性价比高", "confidence": 0.8},
                    {"choice_set_id": 2, "chosen_alt_index": 1, "reasoning": "品牌好", "confidence": 0.9},
                ],
            },
            {
                "response_id": "resp-002",
                "study_id": "dishwasher-202506",
                "persona_id": "persona-dw-002",
                "questionnaire_id": "q-dishwasher-202506",
                "segment": "新手宝妈",
                "responses": [
                    {"choice_set_id": 1, "chosen_alt_index": 2, "reasoning": "容量大", "confidence": 0.7},
                ],
            },
        ]

        questionnaire = {
            "questionnaire_id": "q-dishwasher-202506",
            "study_id": "dishwasher-202506",
            "choice_sets": [
                {
                    "choice_set_id": 1,
                    "alternatives": [
                        {"alt_index": 0, "attributes": {"price": 2999, "brand": "美的"}},
                        {"alt_index": 1, "attributes": {"price": 3999, "brand": "西门子"}},
                        {"alt_index": 2, "attributes": {"price": 4999, "brand": "方太"}},
                    ],
                },
                {
                    "choice_set_id": 2,
                    "alternatives": [
                        {"alt_index": 0, "attributes": {"price": 3499, "brand": "小米"}},
                        {"alt_index": 1, "attributes": {"price": 4599, "brand": "西门子"}},
                        {"alt_index": 2, "attributes": {"price": 5299, "brand": "方太"}},
                    ],
                },
            ],
            "design_parameters": {"n_choice_sets": 2, "n_alternatives": 3},
        }

        attributes = [
            {"id": "price", "name": "价格", "type": "price", "levels": [{"value": 2999, "label": "2999"}]},
            {"id": "brand", "name": "品牌", "type": "categorical", "levels": [{"value": "美的", "label": "美的"}]},
        ]

        result = call_tool(
            "responses_to_raw_dataset",
            responses=responses,
            study_id="dishwasher-202506",
            attributes=attributes,
            questionnaire=questionnaire,
        )

        assert result.is_success is True
        dataset = result.data
        assert "metadata" in dataset
        assert "choice_records" in dataset
        assert dataset["metadata"]["n_respondents"] == 2
        assert dataset["metadata"]["n_choice_sets"] == 2
        # Each respondent has 2 choice records
        assert len(dataset["choice_records"]) == 4

        # Check first respondent's first choice
        first_record = dataset["choice_records"][0]
        assert first_record["respondent_id"] == "persona-dw-001"
        assert first_record["choice_set_id"] == 1
        assert first_record["alternatives"][0]["chosen"] is True
        assert first_record["alternatives"][1]["chosen"] is False

    def test_responses_to_raw_dataset_empty_raises(self) -> None:
        """Test that empty responses raises ValueError."""
        result = call_tool(
            "responses_to_raw_dataset",
            responses=[],
            study_id="test",
            attributes=[],
            questionnaire={"choice_sets": [], "design_parameters": {}},
        )
        assert result.status == ToolCallStatus.ERROR
        assert "cannot be empty" in result.error

    def test_analysis_result_to_report_context(self) -> None:
        """Test AnalysisResult → report context transformation."""
        analysis_result = {
            "analysis_id": "ar-dishwasher-202506",
            "study_id": "dishwasher-202506",
            "status": "COMPLETED",
            "model_type": "hb",
            "convergence": {
                "rhat_max": 1.04,
                "rhat_by_param": {},
                "ess_bulk_min": 1200,
                "ess_tail_min": 1100,
                "ess_by_param": {},
                "converged": True,
                "reliable_ess": True,
                "divergences": 0,
                "tree_depth_max": 10,
            },
            "population_params": {
                "mu": {"price": -0.002, "brand_0": 0.5},
                "sigma": {"price": 0.001, "brand_0": 0.3},
            },
            "individual_utilities": {
                "persona-dw-001": {"price": -0.002, "brand_0": 0.5},
            },
            "importance": {"price": 0.425, "brand": 0.238, "capacity": 0.152},
            "wtp": {
                "wtp_values": {
                    "capacity": {
                        "comparisons": [
                            {
                                "from_level": "6套",
                                "to_level": "10套",
                                "wtp_mean": 800,
                                "wtp_median": 750,
                                "wtp_std": 200,
                                "ci_95_lower": 400,
                                "ci_95_upper": 1200,
                                "n_valid": 150,
                            }
                        ]
                    }
                },
                "price_coefficient_summary": {
                    "mean": -0.002,
                    "median": -0.002,
                    "std": 0.001,
                    "negative_rate": 0.95,
                    "n_positive_outliers": 5,
                },
            },
            "processing_time_seconds": 45.2,
        }

        attributes = [
            {"id": "price", "name": "价格", "type": "price"},
            {"id": "brand", "name": "品牌", "type": "categorical"},
            {"id": "capacity", "name": "容量", "type": "categorical"},
        ]

        result = call_tool(
            "analysis_result_to_report_context",
            analysis_result=analysis_result,
            attributes=attributes,
        )

        assert result.is_success is True
        ctx = result.data
        assert "summary" in ctx
        assert "key_findings" in ctx
        assert "charts_data" in ctx
        assert "recommendations" in ctx

        # Check findings
        findings = ctx["key_findings"]
        assert any("价格" in f for f in findings)
        assert any("收敛" in f for f in findings)

        # Check charts data
        charts = ctx["charts_data"]
        assert "importance" in charts
        assert charts["importance"]["labels"][0] == "价格"  # Most important first

    def test_validate_data_flow_persona_to_dataset(self) -> None:
        """Test PersonaProfile → CBCRawDataset validation."""
        persona = {
            "persona_id": "persona-dw-001",
            "segment": "精致白领",
            "layer1_demographics": {"age": "28岁"},
            "layer2_behavior": {"price_sensitivity": "中高敏感"},
            "layer3_psychology": {
                "tension_combination": {
                    "labels": ["a", "b"],
                    "narrative_explanation": "x" * 50,
                }
            },
            "layer4_scenarios": {"daily_routine": "早9晚7"},
        }

        result = call_tool(
            "validate_data_flow",
            source_type="PersonaProfile",
            target_type="CBCRawDataset",
            data=persona,
        )

        assert result.is_success is True
        assert result.data["valid"] is True
        assert result.data["errors"] == []

    def test_validate_data_flow_missing_fields(self) -> None:
        """Test validation catches missing fields."""
        incomplete_persona = {
            "persona_id": "persona-dw-001",
            # Missing segment, layer fields
        }

        result = call_tool(
            "validate_data_flow",
            source_type="PersonaProfile",
            target_type="CBCRawDataset",
            data=incomplete_persona,
        )

        assert result.is_success is True
        assert result.data["valid"] is False
        assert len(result.data["errors"]) > 0

    def test_validate_data_flow_dataset_to_analysis(self) -> None:
        """Test CBCRawDataset → AnalysisResult validation."""
        dataset = {
            "metadata": {
                "study_id": "dishwasher-202506",
                "n_respondents": 150,
                "n_choice_sets": 12,
                "n_alternatives": 3,
            },
            "choice_records": [
                {
                    "respondent_id": "p-001",
                    "respondent_index": 0,
                    "segment": "精致白领",
                    "choice_set_id": 1,
                    "choice_set_index": 0,
                    "alternatives": [],
                    "none_chosen": False,
                }
            ],
        }

        result = call_tool(
            "validate_data_flow",
            source_type="CBCRawDataset",
            target_type="AnalysisResult",
            data=dataset,
        )

        assert result.is_success is True
        assert result.data["valid"] is True

    def test_validate_data_flow_unknown(self) -> None:
        """Test unknown flow returns error."""
        result = call_tool(
            "validate_data_flow",
            source_type="Unknown",
            target_type="AlsoUnknown",
            data={},
        )

        assert result.is_success is True
        assert result.data["valid"] is False
        assert "Unknown data flow" in result.data["errors"][0]
