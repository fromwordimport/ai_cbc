"""Unit tests for SchemaValidator and LogicValidator."""

import pytest

pytestmark = pytest.mark.unit

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
from aicbc.core.validators import LogicValidator, SchemaValidator, ValidationResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_persona() -> PersonaProfile:
    """Return a fully valid PersonaProfile for baseline tests."""
    return PersonaProfile(
        persona_id="persona-test-001",
        segment="都市新锐",
        layer1_demographics=Layer1Demographics(
            age="25-34",
            gender="男",
            city="一线城市",
            income="月收入20K-30K",
            occupation="互联网从业者",
            education="本科",
            marital_status="未婚",
            living_type="独居",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="中等敏感",
            purchase_channels=["电商平台", "线下门店"],
            decision_style="理性比较",
            brand_loyalty="中等",
            information_source=["社交媒体", "朋友推荐"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率至上", "品质生活"],
            core_anxieties=["时间焦虑"],
            tension_combination=TensionCombination(
                labels=["高收入", "极简主义"],
                narrative_explanation="他虽然在一线城市拿着高薪，但内心深处向往极简生活，"
                "这种矛盾源于童年物质匮乏的经历，让他既渴望用消费证明成功，"
                "又害怕被物质绑架失去自由。",
            ),
            secret_motivation="渴望被认可为独立思考者",
            defense_mechanism="理性化",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="早9晚7，周末健身",
            purchase_trigger="搬家或设备老化",
            stress_response="做详细对比表格",
            social_behavior="小圈子深度社交",
        ),
        language_samples=[
            "洗碗机真是解放双手的神器，每天省下半小时太值了。",
            "我比较看重能耗等级，长期使用电费也是一笔开销。",
            "品牌口碑很重要，朋友推荐比广告更让我信任。",
        ],
        dishwasher_context=DishwasherContext(
            purchase_constraints=["厨房空间有限"],
            decision_factors=["洗净效果", "噪音水平"],
            ignored_factors=["外观设计"],
        ),
        authenticity_score=10.5,
        generation_metadata=GenerationMetadata(
            model="gpt-4o", version="1.0", seed=42, cost_cny=0.5
        ),
    )


@pytest.fixture
def schema_validator() -> SchemaValidator:
    """Return a fresh SchemaValidator instance."""
    return SchemaValidator()


@pytest.fixture
def logic_validator() -> LogicValidator:
    """Return a fresh LogicValidator instance."""
    return LogicValidator()


# ---------------------------------------------------------------------------
# SchemaValidator tests
# ---------------------------------------------------------------------------


class TestSchemaValidator:
    """Tests for SchemaValidator."""

    def test_valid_persona_passes(
        self, schema_validator: SchemaValidator, valid_persona: PersonaProfile
    ) -> None:
        """A fully valid persona should pass schema validation."""
        result = schema_validator.validate(valid_persona)
        assert result.passed is True
        assert result.errors == []

    def test_missing_persona_id(
        self, schema_validator: SchemaValidator, valid_persona: PersonaProfile
    ) -> None:
        """Missing persona_id should fail."""
        valid_persona.persona_id = ""
        result = schema_validator.validate(valid_persona)
        assert result.passed is False
        assert any("persona_id" in e for e in result.errors)

    def test_missing_segment(
        self, schema_validator: SchemaValidator, valid_persona: PersonaProfile
    ) -> None:
        """Missing segment should fail."""
        valid_persona.segment = "   "
        result = schema_validator.validate(valid_persona)
        assert result.passed is False
        assert any("segment" in e for e in result.errors)

    def test_invalid_gender(
        self, schema_validator: SchemaValidator, valid_persona: PersonaProfile
    ) -> None:
        """Gender outside allowed enum should fail."""
        valid_persona.layer1_demographics.gender = "未知"
        result = schema_validator.validate(valid_persona)
        assert result.passed is False
        assert any("gender" in e for e in result.errors)

    def test_invalid_city(
        self, schema_validator: SchemaValidator, valid_persona: PersonaProfile
    ) -> None:
        """City outside allowed enum should fail."""
        valid_persona.layer1_demographics.city = "五线"
        result = schema_validator.validate(valid_persona)
        assert result.passed is False
        assert any("city" in e for e in result.errors)

    def test_language_samples_wrong_count(
        self, schema_validator: SchemaValidator, valid_persona: PersonaProfile
    ) -> None:
        """language_samples must be exactly 3."""
        valid_persona.language_samples = valid_persona.language_samples[:2]
        result = schema_validator.validate(valid_persona)
        assert result.passed is False
        assert any("language_samples" in e and "3" in e for e in result.errors)

    def test_core_values_empty(
        self, schema_validator: SchemaValidator, valid_persona: PersonaProfile
    ) -> None:
        """core_values must have at least 1 item."""
        valid_persona.layer3_psychology.core_values = []
        result = schema_validator.validate(valid_persona)
        assert result.passed is False
        assert any("core_values" in e for e in result.errors)

    def test_authenticity_score_out_of_range(
        self, schema_validator: SchemaValidator, valid_persona: PersonaProfile
    ) -> None:
        """authenticity_score must be 0-14."""
        valid_persona.authenticity_score = 15.0
        result = schema_validator.validate(valid_persona)
        assert result.passed is False
        assert any("authenticity_score" in e for e in result.errors)

    def test_narrative_too_short(
        self, schema_validator: SchemaValidator, valid_persona: PersonaProfile
    ) -> None:
        """narrative_explanation must be >= 50 chars."""
        valid_persona.layer3_psychology.tension_combination.narrative_explanation = "太短了"
        result = schema_validator.validate(valid_persona)
        assert result.passed is False
        assert any("narrative_explanation" in e for e in result.errors)

    def test_missing_layer1_field(
        self, schema_validator: SchemaValidator, valid_persona: PersonaProfile
    ) -> None:
        """Empty required field in layer1 should fail."""
        valid_persona.layer1_demographics.age = ""
        result = schema_validator.validate(valid_persona)
        assert result.passed is False
        assert any("layer1_demographics.age" in e for e in result.errors)

    def test_missing_layer4_field(
        self, schema_validator: SchemaValidator, valid_persona: PersonaProfile
    ) -> None:
        """Empty required field in layer4 should fail."""
        valid_persona.layer4_scenarios.stress_response = None  # type: ignore[assignment]
        result = schema_validator.validate(valid_persona)
        assert result.passed is False
        assert any("stress_response" in e for e in result.errors)


# ---------------------------------------------------------------------------
# LogicValidator tests
# ---------------------------------------------------------------------------


class TestLogicValidator:
    """Tests for LogicValidator."""

    def test_valid_persona_passes_all_rules(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """A fully valid persona should score 6/6."""
        result = logic_validator.validate(valid_persona)
        assert result.score == 7.0
        assert result.details["max_possible_score"] == 7.0
        assert all(s == 1.0 for s in result.details["rule_scores"].values())

    def test_rule_001_narrative_too_short(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-001: narrative < 50 chars should fail."""
        valid_persona.layer3_psychology.tension_combination.narrative_explanation = "太短"
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-001"] == 0.0
        assert any("RULE-001" in e for e in result.errors)

    def test_rule_002_tier1_low_income(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-002: 一线城市 + 月收入<5K should fail."""
        valid_persona.layer1_demographics.city = "一线城市"
        valid_persona.layer1_demographics.income = "月收入<5K"
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-002"] == 0.0
        assert any("RULE-002" in e for e in result.errors)

    def test_rule_002_xinyixian_low_income(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-002: 新一线 + 月收入<5K should also fail."""
        valid_persona.layer1_demographics.city = "新一线城市"
        valid_persona.layer1_demographics.income = "月收入<5K"
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-002"] == 0.0

    def test_rule_002_valid_combination(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-002: 四线 + 月收入<5K should pass."""
        valid_persona.layer1_demographics.city = "四线"
        valid_persona.layer1_demographics.income = "月收入<5K"
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-002"] == 1.0

    def test_rule_003_student_high_income(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-003: 学生 + 月收入30K+ should fail."""
        valid_persona.layer1_demographics.occupation = "学生"
        valid_persona.layer1_demographics.income = "月收入30K+"
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-003"] == 0.0
        assert any("RULE-003" in e and "学生" in e for e in result.errors)

    def test_rule_003_retiree_high_income(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-003: 退休 + 月收入30K+ should fail."""
        valid_persona.layer1_demographics.occupation = "退休"
        valid_persona.layer1_demographics.income = "月收入30K+"
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-003"] == 0.0
        assert any("退休" in e for e in result.errors)

    def test_rule_003_normal_combination(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-003: 学生 + 月收入<5K should pass."""
        valid_persona.layer1_demographics.occupation = "学生"
        valid_persona.layer1_demographics.income = "月收入<5K"
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-003"] == 1.0

    def test_rule_004_frugality_impulse(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-004: 极端节俭 + 冲动消费 should fail."""
        valid_persona.layer2_behavior.price_sensitivity = "极端节俭"
        valid_persona.layer2_behavior.decision_style = "冲动消费"
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-004"] == 0.0
        assert any("RULE-004" in e for e in result.errors)

    def test_rule_004_high_sensitivity_luxury(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-004: 高敏感 + 奢侈追求 should fail."""
        valid_persona.layer2_behavior.price_sensitivity = "高敏感"
        valid_persona.layer2_behavior.decision_style = "奢侈追求"
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-004"] == 0.0

    def test_rule_004_consistent(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-004: 中等敏感 + 理性比较 should pass."""
        valid_persona.layer2_behavior.price_sensitivity = "中等敏感"
        valid_persona.layer2_behavior.decision_style = "理性比较"
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-004"] == 1.0

    def test_rule_005_sample_too_short(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-005: language sample < 20 chars should fail."""
        valid_persona.language_samples = [
            "洗碗机真好用啊",
            "我比较看重能耗等级，长期使用电费也是一笔开销。",
            "品牌口碑很重要，朋友推荐比广告更让我信任。",
        ]
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-005"] == 0.0
        assert any("RULE-005" in e for e in result.errors)

    def test_rule_005_sample_too_long(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-005: language sample > 60 chars should fail."""
        valid_persona.language_samples = [
            "洗碗机真是解放双手的神器，每天省下半小时太值了。",
            "我比较看重能耗等级，长期使用电费也是一笔不小的开销，必须精打细算才能对得起自己辛苦赚来的每一分钱，毕竟环保节能也非常重要。",
            "品牌口碑很重要，朋友推荐比广告更让我信任。",
        ]
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-005"] == 0.0

    def test_rule_006_forbidden_term(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-006: language sample containing 'AI' should fail."""
        valid_persona.language_samples = [
            "这个洗碗机用了AI算法，感觉特别智能。",
            "我比较看重能耗等级，长期使用电费也是一笔开销。",
            "品牌口碑很重要，朋友推荐比广告更让我信任。",
        ]
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-006"] == 0.0
        assert any("RULE-006" in e and "AI" in e for e in result.errors)

    def test_rule_006_forbidden_suanfa(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """RULE-006: language sample containing '算法' should fail."""
        valid_persona.language_samples = [
            "这个洗碗机的算法很先进，洗得特别干净。",
            "我比较看重能耗等级，长期使用电费也是一笔开销。",
            "品牌口碑很重要，朋友推荐比广告更让我信任。",
        ]
        result = logic_validator.validate(valid_persona)
        assert result.details["rule_scores"]["RULE-006"] == 0.0
        assert any("算法" in e for e in result.errors)

    def test_multiple_rule_failures(
        self, logic_validator: LogicValidator, valid_persona: PersonaProfile
    ) -> None:
        """Multiple rule failures should all be reported with partial score."""
        valid_persona.layer1_demographics.city = "一线城市"
        valid_persona.layer1_demographics.income = "月收入<5K"
        valid_persona.layer2_behavior.price_sensitivity = "极端节俭"
        valid_persona.layer2_behavior.decision_style = "冲动消费"
        result = logic_validator.validate(valid_persona)
        assert result.score == 5.0  # RULE-001, 003, 005, 006, 007 pass; 002, 004 fail
        assert len(result.errors) == 2


# ---------------------------------------------------------------------------
# ValidationResult tests
# ---------------------------------------------------------------------------


class TestValidationResult:
    """Tests for ValidationResult dataclass utilities."""

    def test_default_passed(self) -> None:
        """Default ValidationResult should pass."""
        vr = ValidationResult()
        assert vr.passed is True
        assert vr.errors == []
        assert vr.score is None

    def test_add_error(self) -> None:
        """Adding an error should set passed to False."""
        vr = ValidationResult()
        vr.add_error("Something went wrong")
        assert vr.passed is False
        assert vr.errors == ["Something went wrong"]

    def test_merge(self) -> None:
        """Merging should combine errors and details."""
        vr1 = ValidationResult()
        vr1.add_error("Error A")
        vr1.details["foo"] = "bar"

        vr2 = ValidationResult()
        vr2.add_error("Error B")
        vr2.details["baz"] = "qux"

        merged = vr1.merge(vr2)
        assert merged.passed is False
        assert "Error A" in merged.errors
        assert "Error B" in merged.errors
        assert merged.details == {"foo": "bar", "baz": "qux"}
