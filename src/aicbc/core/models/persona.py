"""Persona profile Pydantic models — four-layer consumer persona."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Layer1Demographics(BaseModel):
    """Layer 1: Demographics — identity tags."""

    age: str = Field(..., description="年龄段")
    gender: str = Field(..., description="性别")
    city: str = Field(..., description="现居城市/区域")
    income: str = Field(..., description="个人年收入档位")
    occupation: str = Field(..., description="职业")
    education: str = Field(..., description="教育程度")
    marital_status: str = Field(..., description="婚姻状况")
    living_type: str = Field(..., description="居住形态")

    model_config = {"json_schema_extra": {"layer": 1, "layer_name": "demographics"}}


class Layer2Behavior(BaseModel):
    """Layer 2: Consumer behavior — core tags."""

    price_sensitivity: str = Field(..., description="价格敏感度")
    purchase_channels: list[str] = Field(default_factory=list, description="常用购买渠道")
    decision_style: str = Field(..., description="决策风格")
    brand_loyalty: str = Field(..., description="品牌忠诚度")
    information_source: list[str] = Field(default_factory=list, description="信息来源")

    model_config = {"json_schema_extra": {"layer": 2, "layer_name": "behavior"}}


class TensionCombination(BaseModel):
    """Tension combination with narrative explanation."""

    labels: list[str] = Field(default_factory=list, description="矛盾标签组合")
    narrative_explanation: str = Field(
        ...,
        description="对张力组合的心理叙事解释",
        min_length=50,
    )

    @field_validator("narrative_explanation")
    @classmethod
    def _validate_narrative_length(cls, v: str) -> str:
        if len(v.strip()) < 50:
            raise ValueError("narrative_explanation must be at least 50 characters")
        return v


class Layer3Psychology(BaseModel):
    """Layer 3: Psychology — soul tags."""

    core_values: list[str] = Field(default_factory=list, description="核心价值观")
    core_anxieties: list[str] = Field(default_factory=list, description="核心焦虑")
    tension_combination: TensionCombination = Field(..., description="张力组合与解释")
    secret_motivation: str = Field(..., description="隐藏动机")
    defense_mechanism: str = Field(..., description="心理防御机制")

    model_config = {"json_schema_extra": {"layer": 3, "layer_name": "psychology"}}


class Layer4Scenarios(BaseModel):
    """Layer 4: Scenarios — situational tags."""

    daily_routine: str = Field(..., description="日常生活轨迹")
    purchase_trigger: str = Field(..., description="购买触发事件")
    stress_response: str = Field(..., description="压力下的反应")
    social_behavior: str = Field(..., description="社交行为特征")

    model_config = {"json_schema_extra": {"layer": 4, "layer_name": "scenarios"}}


class DishwasherContext(BaseModel):
    """Dishwasher purchase context — product-specific situation."""

    purchase_constraints: list[str] = Field(default_factory=list, description="购买约束")
    decision_factors: list[str] = Field(default_factory=list, description="决策因素")
    ignored_factors: list[str] = Field(default_factory=list, description="忽略因素")


class GenerationMetadata(BaseModel):
    """Metadata about persona generation."""

    model: str = Field(default="", description="生成模型")
    version: str = Field(default="", description="模型版本")
    seed: int | None = Field(default=None, description="随机种子")
    cost_cny: float = Field(default=0.0, description="生成成本（元）")


class PersonaProfile(BaseModel):
    """Complete four-layer virtual consumer persona."""

    persona_id: str = Field(
        ...,
        description="全局唯一画像标识，格式：前缀 + study_id + 序号",
        pattern=r"^persona-[a-z0-9]+-\d+$",
    )
    segment: str = Field(..., description="所属细分群体")
    layer1_demographics: Layer1Demographics = Field(..., description="人口统计层")
    layer2_behavior: Layer2Behavior = Field(..., description="消费行为层")
    layer3_psychology: Layer3Psychology = Field(..., description="心理动机层")
    layer4_scenarios: Layer4Scenarios = Field(..., description="情境叙事层")
    language_samples: list[str] = Field(
        default_factory=list,
        description="代表性发言（3条），单条20-60字",
    )
    dishwasher_context: DishwasherContext = Field(..., description="洗碗机购买情境")
    authenticity_score: float | None = Field(
        default=None,
        description="真实性评分（0-14），≥9为及格，≥12为优秀",
        ge=0,
        le=14,
    )
    bias_audit_status: str = Field(
        default="PENDING",
        description="偏见审计状态",
        pattern=r"^(PASSED|FAILED|PENDING)$",
    )
    generation_metadata: GenerationMetadata = Field(
        default_factory=GenerationMetadata,
        description="生成元信息",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="创建时间（UTC）",
    )

    @field_validator("language_samples")
    @classmethod
    def _validate_language_samples(cls, v: list[str]) -> list[str]:
        if len(v) != 3:
            raise ValueError("language_samples must contain exactly 3 samples")
        for sample in v:
            length = len(sample.strip())
            if not (20 <= length <= 60):
                raise ValueError(
                    f"Each language sample must be 20-60 characters, got {length}"
                )
        return v

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return self.model_dump(mode="json")

    def get_layer(self, layer_number: int) -> BaseModel:
        """Get a specific layer by number (1-4)."""
        layers = {
            1: self.layer1_demographics,
            2: self.layer2_behavior,
            3: self.layer3_psychology,
            4: self.layer4_scenarios,
        }
        if layer_number not in layers:
            raise ValueError(f"Invalid layer number: {layer_number}, must be 1-4")
        return layers[layer_number]
