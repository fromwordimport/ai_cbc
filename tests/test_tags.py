"""Tests for tag system JSON schemas, Pydantic models, and tag loader."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aicbc.core.models.persona import (
    DishwasherContext,
    GenerationMetadata,
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
    PersonaProfile,
    TensionCombination,
)
from aicbc.utils.tag_loader import (
    TAG_SCHEMA_NAMES,
    get_dimension_options,
    list_dimensions,
    load_all_tag_schemas,
    load_tag_schema,
    validate_tag_value,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAGS_DIR = PROJECT_ROOT / "configs" / "tags"


# ---------------------------------------------------------------------------
# JSON schema file tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("schema_name", TAG_SCHEMA_NAMES)
def test_tag_json_file_exists(schema_name: str) -> None:
    """Each schema JSON file must exist."""
    path = TAGS_DIR / f"{schema_name}.json"
    assert path.exists(), f"Missing schema file: {path}"


@pytest.mark.parametrize("schema_name", TAG_SCHEMA_NAMES)
def test_tag_json_valid(schema_name: str) -> None:
    """Each schema JSON must be valid and contain required keys."""
    path = TAGS_DIR / f"{schema_name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "schema_version" in data
    assert "schema_name" in data
    assert "description" in data
    assert "dimensions" in data
    assert isinstance(data["dimensions"], list)
    assert len(data["dimensions"]) > 0


def test_demographics_has_eight_dimensions() -> None:
    """Demographics schema must contain exactly 8 dimensions."""
    data = load_tag_schema("demographics")
    assert len(data["dimensions"]) == 8
    dim_ids = {d["id"] for d in data["dimensions"]}
    assert dim_ids == {
        "age",
        "gender",
        "city",
        "income",
        "occupation",
        "education",
        "marital_status",
        "living_type",
    }


def test_behaviors_has_five_dimensions() -> None:
    """Behaviors schema must contain exactly 5 dimensions."""
    data = load_tag_schema("behaviors")
    assert len(data["dimensions"]) == 5
    dim_ids = {d["id"] for d in data["dimensions"]}
    assert dim_ids == {
        "price_sensitivity",
        "purchase_channels",
        "decision_style",
        "brand_loyalty",
        "information_source",
    }


def test_psychologies_has_five_dimensions() -> None:
    """Psychologies schema must contain exactly 5 dimensions."""
    data = load_tag_schema("psychologies")
    assert len(data["dimensions"]) == 5
    dim_ids = {d["id"] for d in data["dimensions"]}
    assert dim_ids == {
        "core_values",
        "core_anxieties",
        "tension_combination",
        "secret_motivation",
        "defense_mechanism",
    }


def test_scenarios_has_four_dimensions() -> None:
    """Scenarios schema must contain exactly 4 dimensions."""
    data = load_tag_schema("scenarios")
    assert len(data["dimensions"]) == 4
    dim_ids = {d["id"] for d in data["dimensions"]}
    assert dim_ids == {
        "daily_routine",
        "purchase_trigger",
        "stress_response",
        "social_behavior",
    }


# ---------------------------------------------------------------------------
# Tag loader tests
# ---------------------------------------------------------------------------


def test_load_all_tag_schemas() -> None:
    """Loader must return all four schemas."""
    schemas = load_all_tag_schemas()
    assert set(schemas.keys()) == set(TAG_SCHEMA_NAMES)


def test_load_tag_schema_unknown() -> None:
    """Loading an unknown schema must raise ValueError."""
    with pytest.raises(ValueError, match="Unknown schema"):
        load_tag_schema("unknown_schema")


def test_load_tag_schema_missing_file(tmp_path: Path) -> None:
    """Loading from a missing file must raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_tag_schema("demographics", tags_dir=tmp_path)


def test_get_dimension_options() -> None:
    """Options for 'age' dimension must match expected values."""
    options = get_dimension_options("demographics", "age")
    assert "18-24岁" in options
    assert "25-34岁" in options


def test_get_dimension_options_not_found() -> None:
    """Requesting a non-existent dimension must raise ValueError."""
    with pytest.raises(ValueError, match="not found"):
        get_dimension_options("demographics", "nonexistent")


def test_list_dimensions() -> None:
    """list_dimensions must return the dimensions list."""
    dims = list_dimensions("behaviors")
    assert isinstance(dims, list)
    assert len(dims) == 5


def test_validate_tag_value_single() -> None:
    """Single-select validation must work correctly."""
    assert validate_tag_value("demographics", "gender", "女") is True
    assert validate_tag_value("demographics", "gender", "外星人") is False


def test_validate_tag_value_multi() -> None:
    """Multi-select validation must work correctly."""
    assert (
        validate_tag_value(
            "behaviors", "purchase_channels", ["线下-便利店", "货架电商（淘宝/天猫/京东/拼多多）"]
        )
        is True
    )
    assert validate_tag_value("behaviors", "purchase_channels", ["不存在渠道"]) is False


def test_validate_tag_value_free_text() -> None:
    """Free-text dimensions (no options) must accept non-empty strings."""
    assert validate_tag_value("scenarios", "daily_routine", "早起通勤上班") is True
    assert validate_tag_value("scenarios", "daily_routine", "") is False


# ---------------------------------------------------------------------------
# Pydantic model tests — Layer 1
# ---------------------------------------------------------------------------


def test_layer1_demographics_valid() -> None:
    """Layer1Demographics must accept valid data."""
    layer = Layer1Demographics(
        age="25-34岁",
        gender="女",
        city="新一线城市",
        income="15-30万元",
        occupation="企业职员",
        education="本科",
        marital_status="已婚无子女",
        living_type="租房",
    )
    assert layer.age == "25-34岁"
    assert layer.gender == "女"


def test_layer1_demographics_missing_field() -> None:
    """Missing required field must raise ValidationError."""
    with pytest.raises(ValidationError):
        Layer1Demographics(
            age="25-34岁",
            gender="女",
            # missing other fields
        )


# ---------------------------------------------------------------------------
# Pydantic model tests — Layer 2
# ---------------------------------------------------------------------------


def test_layer2_behavior_valid() -> None:
    """Layer2Behavior must accept valid data."""
    layer = Layer2Behavior(
        price_sensitivity="比价工具用户（慢慢买/什么值得买）",
        purchase_channels=["货架电商（淘宝/天猫/京东/拼多多）", "内容电商（抖音/快手/小红书/视频号）"],
        decision_style="果断独立",
        brand_loyalty="2-3个品牌间选择",
        information_source=["小红书", "知乎"],
    )
    assert layer.decision_style == "果断独立"
    assert len(layer.purchase_channels) == 2


def test_layer2_behavior_defaults() -> None:
    """Layer2Behavior must provide default empty lists."""
    layer = Layer2Behavior(
        price_sensitivity="不在乎价格波动",
        decision_style="果断独立",
        brand_loyalty="完全无品牌偏好（只看产品/价格）",
    )
    assert layer.purchase_channels == []
    assert layer.information_source == []


# ---------------------------------------------------------------------------
# Pydantic model tests — Layer 3
# ---------------------------------------------------------------------------


def test_tension_combination_valid() -> None:
    """TensionCombination must accept valid data with narrative >= 50 chars."""
    tc = TensionCombination(
        labels=["收入高", "极简主义", "对促销高度敏感"],
        narrative_explanation="她年薪五十万却坚持极简生活，表面上是理性消费的选择，实则是童年物质匮乏经历在她心理上留下的深刻烙印，一种通过控制消费来获得安全感的补偿机制。",
    )
    assert len(tc.narrative_explanation) >= 50


def test_tension_combination_short_narrative() -> None:
    """TensionCombination with short narrative must raise ValidationError."""
    with pytest.raises(ValidationError):
        TensionCombination(
            labels=["标签A", "标签B"],
            narrative_explanation="太短了",
        )


def test_layer3_psychology_valid() -> None:
    """Layer3Psychology must accept valid data."""
    layer = Layer3Psychology(
        core_values=["效率", "品质生活"],
        core_anxieties=["时间不够用", "家务分工矛盾"],
        tension_combination=TensionCombination(
            labels=["精致品质", "凑单退单高手"],
            narrative_explanation="她追求精致生活却总在凑单后退掉不需要的商品，这种表面矛盾实际上是她内心深处既渴望品质生活又极度害怕浪费金钱的心理拉锯战。",
        ),
        secret_motivation="用科技产品证明自己的生活品味",
        defense_mechanism="合理化：说服自己这是长期投资",
    )
    assert layer.secret_motivation == "用科技产品证明自己的生活品味"


# ---------------------------------------------------------------------------
# Pydantic model tests — Layer 4
# ---------------------------------------------------------------------------


def test_layer4_scenarios_valid() -> None:
    """Layer4Scenarios must accept valid data."""
    layer = Layer4Scenarios(
        daily_routine="早9晚7，周末打扫，晚上追剧",
        purchase_trigger="看到同事晒洗碗机，心动",
        stress_response="焦虑时更容易冲动消费",
        social_behavior="爱在社交媒体分享好物",
    )
    assert "早9晚7" in layer.daily_routine


# ---------------------------------------------------------------------------
# Pydantic model tests — PersonaProfile
# ---------------------------------------------------------------------------


def _make_valid_persona() -> PersonaProfile:
    """Helper to create a fully valid PersonaProfile."""
    return PersonaProfile(
        persona_id="persona-dw-001",
        segment="精致白领",
        layer1_demographics=Layer1Demographics(
            age="28岁",
            gender="女",
            city="新一线城市",
            income="月收入15K-25K",
            occupation="互联网运营",
            education="本科",
            marital_status="已婚无孩",
            living_type="70㎡两居室，租房",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="中高敏感",
            purchase_channels=["京东", "天猫", "线下苏宁"],
            decision_style="理性比较型",
            brand_loyalty="中等，重性价比",
            information_source=["小红书", "知乎", "朋友推荐"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率", "品质生活"],
            core_anxieties=["时间不够用", "家务分工矛盾"],
            tension_combination=TensionCombination(
                labels=["追求品质", "精打细算"],
                narrative_explanation="她追求高品质生活却又极度精打细算，这种表面上的消费矛盾实际上是她对自我价值认同的一种深层心理保护机制，用来平衡理想与现实之间的巨大落差。",
            ),
            secret_motivation="用科技产品证明自己的生活品味",
            defense_mechanism="合理化：说服自己这是长期投资",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="早9晚7，周末打扫，晚上追剧",
            purchase_trigger="看到同事晒洗碗机，心动",
            stress_response="焦虑时更容易冲动消费",
            social_behavior="爱在社交媒体分享好物",
        ),
        language_samples=[
            "洗碗机真的是解放双手的神器，后悔没早买！",
            "对比了三个品牌，最后还是选了性价比最高的那款。",
            "安装师傅非常专业，只用了半小时就全部搞定了。",
        ],
        dishwasher_context=DishwasherContext(
            purchase_constraints=["厨房空间小", "租房不能大改"],
            decision_factors=["价格", "品牌口碑", "安装便捷性"],
            ignored_factors=["能耗等级", "智能功能"],
        ),
        authenticity_score=11.0,
        bias_audit_status="PASSED",
        generation_metadata=GenerationMetadata(
            model="claude-sonnet-4-6",
            version="1.0.0",
            seed=42,
            cost_cny=2.5,
        ),
    )


def test_persona_profile_valid() -> None:
    """PersonaProfile must accept fully valid data."""
    persona = _make_valid_persona()
    assert persona.persona_id == "persona-dw-001"
    assert persona.authenticity_score == 11.0
    assert persona.bias_audit_status == "PASSED"


def test_persona_profile_invalid_id_format() -> None:
    """PersonaProfile with invalid persona_id format must raise ValidationError."""
    valid = _make_valid_persona()
    with pytest.raises(ValidationError):
        PersonaProfile(
            **{
                **valid.model_dump(),
                "persona_id": "bad-id",
            }
        )


def test_persona_profile_invalid_bias_status() -> None:
    """PersonaProfile with invalid bias_audit_status must raise ValidationError."""
    valid = _make_valid_persona()
    with pytest.raises(ValidationError):
        PersonaProfile(
            **{
                **valid.model_dump(),
                "bias_audit_status": "UNKNOWN",
            }
        )


def test_persona_profile_authenticity_out_of_range() -> None:
    """Authenticity score outside 0-14 must raise ValidationError."""
    valid = _make_valid_persona()
    with pytest.raises(ValidationError):
        PersonaProfile(
            **{
                **valid.model_dump(),
                "authenticity_score": 20.0,
            }
        )


def test_persona_profile_language_samples_count() -> None:
    """Language samples must contain exactly 3 items."""
    valid = _make_valid_persona()
    with pytest.raises(ValidationError, match="exactly 3"):
        PersonaProfile(
            **{
                **valid.model_dump(),
                "language_samples": ["只有一条"],
            }
        )


def test_persona_profile_language_samples_length() -> None:
    """Each language sample must be 20-60 characters."""
    valid = _make_valid_persona()
    with pytest.raises(ValidationError, match="20-60 characters"):
        PersonaProfile(
            **{
                **valid.model_dump(),
                "language_samples": [
                    "太短",
                    "这条长度刚刚好，符合要求。",
                    "这条也符合要求。",
                ],
            }
        )


def test_persona_profile_to_dict() -> None:
    """to_dict must return a serializable dictionary."""
    persona = _make_valid_persona()
    d = persona.to_dict()
    assert isinstance(d, dict)
    assert d["persona_id"] == "persona-dw-001"
    assert "layer1_demographics" in d


def test_persona_profile_get_layer() -> None:
    """get_layer must return the correct layer model."""
    persona = _make_valid_persona()
    assert isinstance(persona.get_layer(1), Layer1Demographics)
    assert isinstance(persona.get_layer(2), Layer2Behavior)
    assert isinstance(persona.get_layer(3), Layer3Psychology)
    assert isinstance(persona.get_layer(4), Layer4Scenarios)


def test_persona_profile_get_layer_invalid() -> None:
    """get_layer with invalid number must raise ValueError."""
    persona = _make_valid_persona()
    with pytest.raises(ValueError, match="Invalid layer number"):
        persona.get_layer(5)


# ---------------------------------------------------------------------------
# Integration: models align with JSON schemas
# ---------------------------------------------------------------------------


def test_model_fields_align_with_schema_dimensions() -> None:
    """Pydantic model fields should align with JSON schema dimensions."""
    # Layer 1
    demo_schema = load_tag_schema("demographics")
    schema_ids = {d["id"] for d in demo_schema["dimensions"]}
    model_fields = set(Layer1Demographics.model_fields.keys())
    assert schema_ids == model_fields, f"Mismatch: {schema_ids.symmetric_difference(model_fields)}"

    # Layer 2
    behav_schema = load_tag_schema("behaviors")
    schema_ids = {d["id"] for d in behav_schema["dimensions"]}
    model_fields = set(Layer2Behavior.model_fields.keys())
    assert schema_ids == model_fields, f"Mismatch: {schema_ids.symmetric_difference(model_fields)}"

    # Layer 4
    scen_schema = load_tag_schema("scenarios")
    schema_ids = {d["id"] for d in scen_schema["dimensions"]}
    model_fields = set(Layer4Scenarios.model_fields.keys())
    assert schema_ids == model_fields, f"Mismatch: {schema_ids.symmetric_difference(model_fields)}"
