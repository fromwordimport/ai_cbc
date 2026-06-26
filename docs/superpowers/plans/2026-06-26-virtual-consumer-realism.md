# Virtual Consumer Realism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the virtual consumer realism governance design: derive product context from persona, validate plausibility, make narrative core first-class, generate voice-consistent language samples, and reposition the authenticity scorer as a diagnostic probe.

**Architecture:** Add `PlausibilityValidator`, `ProductContextDeriver`, `NarrativeCoreGenerator`, `NarrativeConsistencyChecker`, and `LanguageSampleGenerator` as focused components. Wire them into `ProfileGenerator` and `ConsumerGeneratorAgent` so that plausibility and narrative consistency become hard gates, while the authenticity score is used only for monitoring.

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI, pytest, uv, YAML.

## Global Constraints

- Use `uv` for all Python commands.
- Follow conventional commits (`feat(scope): ...`, `docs(scope): ...`).
- Do not modify existing test files without user authorization (per `CLAUDE.md` Test File Integrity principle). New test files may be created.
- Use Pydantic v2 models with type annotations.
- Use structlog for logging.
- All LLM calls flow through `LLMClient`.
- Bias audit remains the highest-priority gate.
- Prefer focused files with single responsibilities.

## File Structure

| File | Responsibility |
|------|----------------|
| `configs/plausibility_rules/default.yaml` | Business-maintained plausibility rules (student+dorm, etc.). |
| `src/aicbc/core/validators/plausibility_models.py` | Dataclasses/Pydantic models for plausibility findings and results. |
| `src/aicbc/core/validators/plausibility_validator.py` | Loads rules and checks a persona + derived context for situational absurdity. |
| `src/aicbc/core/validators/product_context_models.py` | `DerivedProductContext` model. |
| `src/aicbc/core/validators/product_context_deriver.py` | Derives `dishwasher_context` from the persona + narrative core. |
| `src/aicbc/core/validators/narrative_consistency_checker.py` | Checks whether the mini-biography explains key behavioral tags. |
| `src/aicbc/generators/narrative_core_generator.py` | Generates `MiniBiography` + `SceneReactions` from four layers. |
| `src/aicbc/generators/language_sample_generator.py` | Generates 3 voice-consistent language samples from the narrative core. |
| `configs/prompts/narrative_core_generation.txt` | Prompt template for narrative core generation. |
| `configs/prompts/product_context_derivation.txt` | Prompt template for product context derivation. |
| `configs/prompts/language_sample_generation.txt` | Prompt template for language sample generation. |
| `src/aicbc/core/models/persona.py` | No schema changes in this plan; `mini_biography`/`scene_reactions` remain Optional but are always populated by the new flow. |
| `src/aicbc/generators/profile_generator.py` | Reorder generation: layers → narrative core → product context → plausibility → language samples. |
| `src/aicbc/core/scoring/authenticity_scorer.py` | Add plausibility and narrative-depth dimensions; weaken keyword counting. |
| `src/aicbc/agents/consumer_generator.py` | Reposition correction loop: plausibility first, then narrative, then severe authenticity. |
| `configs/prompts/persona_generation.txt` | Add anti-template constraints. |
| `docs/文档索引与导航.md` | Register new design/plan docs. |

---

## Task 1: Plausibility rules config and validator skeleton

**Files:**
- Create: `configs/plausibility_rules/default.yaml`
- Create: `src/aicbc/core/validators/plausibility_models.py`
- Create: `src/aicbc/core/validators/plausibility_validator.py`
- Create: `tests/unit/core/test_plausibility_validator.py`

**Interfaces:**
- Consumes: `PersonaProfile`, `DerivedProductContext`
- Produces: `PlausibilityResult` with `passed: bool`, `hard_failed: bool`, `findings: list[PlausibilityFinding]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/core/test_plausibility_validator.py`:

```python
"""Tests for PlausibilityValidator."""

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
from aicbc.core.scoring.authenticity_scorer import AuthenticityScorer
from aicbc.core.validators.plausibility_models import PlausibilityFinding, PlausibilityResult
from aicbc.core.validators.plausibility_validator import PlausibilityValidator
from aicbc.core.validators.product_context_models import DerivedProductContext


def _make_persona(**overrides) -> PersonaProfile:
    base = {
        "persona_id": "persona-test-001",
        "segment": "测试群体",
        "layer1_demographics": Layer1Demographics(
            age="20岁",
            gender="男",
            city="二线城市",
            income="3-8万元",
            occupation="大学生",
            education="本科",
            marital_status="未婚",
            living_type="学校宿舍",
        ),
        "layer2_behavior": Layer2Behavior(
            price_sensitivity="高敏感",
            purchase_channels=["拼多多", "食堂"],
            decision_style="拖延比较型",
            brand_loyalty="低",
            information_source=["同学推荐", "小红书"],
        ),
        "layer3_psychology": Layer3Psychology(
            core_values=["省钱", "方便"],
            core_anxieties=["同辈压力"],
            tension_combination=TensionCombination(
                labels=["省钱", "想偷懒"],
                narrative_explanation="他生活费有限，但经常因为想偷懒而点外卖，事后又后悔花钱。这种矛盾让他对能省力的家电既渴望又觉得不配。",
            ),
            secret_motivation="想让室友觉得自己生活有品质",
            defense_mechanism="合理化——把非必要消费说成投资",
        ),
        "layer4_scenarios": Layer4Scenarios(
            daily_routine="早8点上课，中午食堂，晚上宿舍打游戏",
            purchase_trigger="室友推荐",
            stress_response="焦虑时刷购物APP",
            social_behavior="宿舍群活跃",
        ),
        "language_samples": [
            "洗碗机真的好用吗？我没研究过这些。",
            "宿舍那么小，装了也没地方放吧。",
            "要是毕业后自己租房，我可能会考虑。",
        ],
        "dishwasher_context": DishwasherContext(
            purchase_constraints=["厨房空间限制"],
            decision_factors=["价格", "品牌"],
            ignored_factors=["外观设计"],
        ),
        "generation_metadata": GenerationMetadata(),
    }
    base.update(overrides)
    return PersonaProfile(**base)


def test_student_dorm_with_dishwasher_need_is_hard_failure() -> None:
    """A student in a dorm who is marked as considering a dishwasher must fail hard."""
    persona = _make_persona()
    derived = DerivedProductContext(
        eligibility="actively_considering",
        reason=" roommate recommended",
        dishwasher_context=persona.dishwasher_context,
    )
    validator = PlausibilityValidator()
    result = validator.validate(persona, derived)

    assert result.hard_failed is True
    assert result.passed is False
    assert any(f.rule_id == "PLA-001" for f in result.findings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_plausibility_validator.py::test_student_dorm_with_dishwasher_need_is_hard_failure -v`

Expected: FAIL with `ImportError` or `ModuleNotFoundError` for `PlausibilityValidator`.

- [ ] **Step 3: Write minimal implementation**

Create `src/aicbc/core/validators/plausibility_models.py`:

```python
"""Models for plausibility validation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlausibilityFinding:
    """A single plausibility issue."""

    rule_id: str
    severity: str  # "hard" | "soft"
    message: str


@dataclass
class PlausibilityResult:
    """Result of validating a persona's situational plausibility."""

    passed: bool
    hard_failed: bool
    findings: list[PlausibilityFinding] = field(default_factory=list)
```

Create `src/aicbc/core/validators/plausibility_validator.py`:

```python
"""PlausibilityValidator — checks whether a persona's product context is realistic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from aicbc.core.models.persona import PersonaProfile
from aicbc.core.validators.plausibility_models import PlausibilityFinding, PlausibilityResult
from aicbc.core.validators.product_context_models import DerivedProductContext

logger = structlog.get_logger("aicbc.validators")

DEFAULT_RULES_PATH = Path(__file__).parents[3] / "configs" / "plausibility_rules" / "default.yaml"


class PlausibilityValidator:
    """Validate that a persona's product context matches their life situation."""

    def __init__(self, rules_path: Path | str | None = None) -> None:
        self._rules_path = Path(rules_path) if rules_path else DEFAULT_RULES_PATH
        self._rules = self._load_rules()

    def _load_rules(self) -> list[dict[str, Any]]:
        if not self._rules_path.exists():
            logger.warning("plausibility_rules_not_found", path=str(self._rules_path))
            return []
        with self._rules_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data.get("rules", [])

    def validate(
        self,
        persona: PersonaProfile,
        derived_context: DerivedProductContext,
    ) -> PlausibilityResult:
        """Run all active rules against the persona and derived context."""
        findings: list[PlausibilityFinding] = []

        for rule in self._rules:
            if not rule.get("enabled", True):
                continue
            if self._matches(rule, persona, derived_context):
                findings.append(
                    PlausibilityFinding(
                        rule_id=rule["id"],
                        severity=rule["severity"],
                        message=rule["message"],
                    )
                )

        hard_failed = any(f.severity == "hard" for f in findings)
        return PlausibilityResult(
            passed=not hard_failed,
            hard_failed=hard_failed,
            findings=findings,
        )

    def _matches(
        self,
        rule: dict[str, Any],
        persona: PersonaProfile,
        derived_context: DerivedProductContext,
    ) -> bool:
        """Evaluate a single rule's conditions."""
        l1 = persona.layer1_demographics
        conditions = rule.get("conditions", {})

        for key, expected in conditions.items():
            if key == "life_stage_contains":
                if expected not in l1.life_stage:
                    return False
            elif key == "living_type_contains":
                if expected not in l1.living_type:
                    return False
            elif key == "income_contains":
                if expected not in l1.income:
                    return False
            elif key == "eligibility":
                if derived_context.eligibility != expected:
                    return False
            elif key == "eligibility_not":
                if derived_context.eligibility == expected:
                    return False
            elif key == "price_above" and derived_context.dishwasher_context:
                # Price-threshold rules are not implemented in the initial version.
                continue
        return True
```

Create `configs/plausibility_rules/default.yaml`:

```yaml
rules:
  - id: PLA-001
    enabled: true
    severity: hard
    conditions:
      life_stage_contains: "学生"
      living_type_contains: "宿舍"
      eligibility_not: "not_applicable"
    message: "学生住宿舍通常无独立厨房和安装条件，请重新考虑该画像是否真会考虑洗碗机，或把需求改为毕业后租房/买房时才会考虑。"

  - id: PLA-002
    enabled: true
    severity: hard
    conditions:
      income_contains: "3万元以下"
      eligibility: "actively_considering"
    message: "年收入 3 万以下画像若 actively_considering 洗碗机，需有明确的借贷、赠礼或合租分摊叙事。"
```

Add PyYAML to dependencies. Run:

```bash
uv add pyyaml
```

Expected: `pyproject.toml` and `uv.lock` are updated.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_plausibility_validator.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add configs/plausibility_rules/default.yaml \
        src/aicbc/core/validators/plausibility_models.py \
        src/aicbc/core/validators/plausibility_validator.py \
        tests/unit/core/test_plausibility_validator.py
if ! git diff --cached --quiet; then
  git commit -m "feat(validators): add PlausibilityValidator with YAML rule config"
fi
```

---

## Task 2: ProductContextDeriver

**Files:**
- Create: `src/aicbc/core/validators/product_context_models.py`
- Create: `src/aicbc/core/validators/product_context_deriver.py`
- Create: `configs/prompts/product_context_derivation.txt`
- Create: `tests/unit/core/test_product_context_deriver.py`

**Interfaces:**
- Consumes: `PersonaProfile`
- Produces: `DerivedProductContext`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/core/test_product_context_deriver.py`:

```python
"""Tests for ProductContextDeriver."""

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
from aicbc.core.validators.product_context_deriver import ProductContextDeriver
from aicbc.core.validators.product_context_models import DerivedProductContext


def _make_student_dorm_persona() -> PersonaProfile:
    return PersonaProfile(
        persona_id="persona-student-001",
        segment="学生-宿舍",
        layer1_demographics=Layer1Demographics(
            age="20岁",
            gender="男",
            city="二线城市",
            income="3-8万元",
            occupation="大学生",
            education="本科",
            marital_status="未婚",
            living_type="学校宿舍",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="高敏感",
            purchase_channels=["拼多多"],
            decision_style="拖延比较型",
            brand_loyalty="低",
            information_source=["同学推荐"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["省钱"],
            core_anxieties=["同辈压力"],
            tension_combination=TensionCombination(
                labels=["省钱", "想偷懒"],
                narrative_explanation="他生活费有限，但经常因为想偷懒而点外卖，事后又后悔花钱。",
            ),
            secret_motivation="",
            defense_mechanism="",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="早8点上课，晚10点回宿舍",
            purchase_trigger="",
            stress_response="",
            social_behavior="",
        ),
        language_samples=["a" * 20, "b" * 20, "c" * 20],
        dishwasher_context=DishwasherContext(),
        generation_metadata=GenerationMetadata(),
    )


def test_student_dorm_returns_not_applicable() -> None:
    """Physical constraints should short-circuit LLM for impossible cases."""
    deriver = ProductContextDeriver()
    result = deriver.derive(_make_student_dorm_persona())

    assert result.eligibility == "not_applicable"
    assert "宿舍" in result.reason or "独立厨房" in result.reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_product_context_deriver.py::test_student_dorm_returns_not_applicable -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Create `src/aicbc/core/validators/product_context_models.py`:

```python
"""Models for derived product context."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from aicbc.core.models.persona import DishwasherContext


class DerivedProductContext(BaseModel):
    """Product context derived from a persona's life situation."""

    eligibility: Literal["not_applicable", "latent_need", "actively_considering"]
    reason: str
    dishwasher_context: DishwasherContext
```

Create `src/aicbc/core/validators/product_context_deriver.py`:

```python
"""ProductContextDeriver — derive dishwasher context from persona reality."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from aicbc.core.models.persona import DishwasherContext, PersonaProfile
from aicbc.core.validators.product_context_models import DerivedProductContext
from aicbc.llm.client import LLMClient

logger = structlog.get_logger("aicbc.validators")

DEFAULT_PROMPT_PATH = Path(__file__).parents[3] / "configs" / "prompts" / "product_context_derivation.txt"


def _has_independent_kitchen(living_type: str) -> bool:
    """Return False for living situations that physically cannot host a dishwasher."""
    impossible = {"宿舍", "合租房", "无厨房"}
    return not any(marker in living_type for marker in impossible)


class ProductContextDeriver:
    """Derive whether and how a persona would consider a dishwasher."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        prompt_template_path: Path | str | None = None,
    ) -> None:
        self._llm = llm_client or LLMClient()
        self._prompt_path = Path(prompt_template_path) if prompt_template_path else DEFAULT_PROMPT_PATH
        self._template = self._prompt_path.read_text(encoding="utf-8")

    def derive(self, persona: PersonaProfile) -> DerivedProductContext:
        """Return derived product context based on persona reality."""
        l1 = persona.layer1_demographics

        # Hard physical constraints first — no LLM needed.
        if "学生" in l1.life_stage and "宿舍" in l1.living_type:
            return DerivedProductContext(
                eligibility="not_applicable",
                reason="学生住宿舍通常无独立厨房和水电安装条件",
                dishwasher_context=DishwasherContext(
                    purchase_constraints=["无独立厨房，无法安装"],
                    decision_factors=[],
                    ignored_factors=[],
                ),
            )

        if not _has_independent_kitchen(l1.living_type):
            return DerivedProductContext(
                eligibility="not_applicable",
                reason=f"居住形态 '{l1.living_type}' 不具备独立厨房",
                dishwasher_context=DishwasherContext(
                    purchase_constraints=["无独立厨房，无法安装"],
                    decision_factors=[],
                    ignored_factors=[],
                ),
            )

        # Fall back to LLM for nuanced cases.
        prompt = self._build_prompt(persona)
        try:
            response = self._llm.generate(
                messages=[
                    {"role": "system", "content": "你是一个严谨的消费者研究分析师。"},
                    {"role": "user", "content": prompt},
                ],
                json_mode=True,
            )
            parsed = json.loads(response.content)
        except Exception as exc:
            logger.warning("product_context_derivation_failed", error=str(exc), persona_id=persona.persona_id)
            return DerivedProductContext(
                eligibility="not_applicable",
                reason="推导失败，默认认为当前不考虑洗碗机",
                dishwasher_context=DishwasherContext(),
            )

        return DerivedProductContext(
            eligibility=parsed.get("eligibility", "not_applicable"),
            reason=parsed.get("reason", ""),
            dishwasher_context=DishwasherContext(
                purchase_constraints=parsed.get("dishwasher_context", {}).get("purchase_constraints", []),
                decision_factors=parsed.get("dishwasher_context", {}).get("decision_factors", []),
                ignored_factors=parsed.get("dishwasher_context", {}).get("ignored_factors", []),
            ),
        )

    def _build_prompt(self, persona: PersonaProfile) -> str:
        l1 = persona.layer1_demographics
        l2 = persona.layer2_behavior
        l4 = persona.layer4_scenarios
        return (
            "基于以下消费者画像，判断该人物对洗碗机的真实购买可能性，并给出购买情境。\n\n"
            f"人生阶段: {l1.life_stage}\n"
            f"居住形态: {l1.living_type}\n"
            f"收入: {l1.income}\n"
            f"家庭结构: {l1.marital_status}\n"
            f"价格敏感度: {l2.price_sensitivity}\n"
            f"决策风格: {l2.decision_style}\n"
            f"日常轨迹: {l4.daily_routine}\n"
            f"购买触发: {l4.purchase_trigger}\n\n"
            "请严格返回以下 JSON，不要包含 Markdown 代码块：\n"
            '{\n'
            '  "eligibility": "not_applicable" | "latent_need" | "actively_considering",\n'
            '  "reason": "简短理由",\n'
            '  "dishwasher_context": {\n'
            '    "purchase_constraints": ["约束1"],\n'
            '    "decision_factors": ["因素1"],\n'
            '    "ignored_factors": ["忽略1"]\n'
            '  }\n'
            '}'
        )
```

Create `configs/prompts/product_context_derivation.txt` with the same prompt text used in `_build_prompt`:

```text
基于以下消费者画像，判断该人物对洗碗机的真实购买可能性，并给出购买情境。

人生阶段: {{life_stage}}
居住形态: {{living_type}}
收入: {{income}}
家庭结构: {{marital_status}}
价格敏感度: {{price_sensitivity}}
决策风格: {{decision_style}}
日常轨迹: {{daily_routine}}
购买触发: {{purchase_trigger}}

请严格返回以下 JSON，不要包含 Markdown 代码块：
{
  "eligibility": "not_applicable" | "latent_need" | "actively_considering",
  "reason": "简短理由",
  "dishwasher_context": {
    "purchase_constraints": ["约束1"],
    "decision_factors": ["因素1"],
    "ignored_factors": ["忽略1"]
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_product_context_deriver.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add configs/prompts/product_context_derivation.txt \
        src/aicbc/core/validators/product_context_models.py \
        src/aicbc/core/validators/product_context_deriver.py \
        tests/unit/core/test_product_context_deriver.py
git commit -m "feat(validators): add ProductContextDeriver with physical constraints"
```

---

## Task 3: NarrativeCoreGenerator

**Files:**
- Create: `src/aicbc/generators/narrative_core_generator.py`
- Create: `configs/prompts/narrative_core_generation.txt`
- Create: `tests/unit/generators/test_narrative_core_generator.py`

**Interfaces:**
- Consumes: `PersonaProfile` (with layers 1-4)
- Produces: `(MiniBiography, SceneReactions)`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/generators/test_narrative_core_generator.py`:

```python
"""Tests for NarrativeCoreGenerator."""

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
from aicbc.generators.narrative_core_generator import NarrativeCoreGenerator


def _make_persona() -> PersonaProfile:
    return PersonaProfile(
        persona_id="persona-test-001",
        segment="测试群体",
        layer1_demographics=Layer1Demographics(
            age="28岁",
            gender="女",
            city="新一线城市",
            income="15-30万元",
            occupation="互联网产品经理",
            education="本科",
            marital_status="已婚无孩",
            living_type="自有住房（89㎡）",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="中等敏感",
            purchase_channels=["京东", "天猫"],
            decision_style="理性比较型",
            brand_loyalty="中等",
            information_source=["小红书", "知乎"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率", "品质"],
            core_anxieties=["时间不够"],
            tension_combination=TensionCombination(
                labels=["精致品质", "凑单退单"],
                narrative_explanation="她追求精致生活却总在凑单后退掉不需要的商品。",
            ),
            secret_motivation="用科技产品证明品味",
            defense_mechanism="合理化——把消费解释为投资",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="早7点起床，通勤40分钟，晚7点到家",
            purchase_trigger="被小红书种草",
            stress_response="焦虑时刷购物APP",
            social_behavior="朋友圈少发",
        ),
        language_samples=["a" * 20, "b" * 20, "c" * 20],
        dishwasher_context=DishwasherContext(),
        generation_metadata=GenerationMetadata(),
    )


def test_generator_returns_mini_biography_and_scene_reactions(mocker) -> None:
    """Generator should parse LLM output into MiniBiography + SceneReactions."""
    fake_response = mocker.MagicMock()
    fake_response.content = (
        '{\n'
        '  "mini_biography": {\n'
        '    "past": "大学时跟风买奢侈品导致债务危机，形成先研究再购买的习惯。",\n'
        '    "present": "工作日晚上做双十一攻略，周末逛奥特莱斯。",\n'
        '    "future": "担心教育支出挤占品质生活预算。"\n'
        '  },\n'
        '  "scene_reactions": {\n'
        '    "under_pressure": "压力大时加购但不结算",\n'
        '    "friend_recommendation": "先问价格和缺点",\n'
        '    "flash_sale_limited": "设闹钟但常错过",\n'
        '    "found_cheaper_elsewhere": "纠结要不要退货重买",\n'
        '    "product_fault_after_sales": "先小红书查攻略再联系客服"\n'
        '  }\n'
        '}'
    )

    gen = NarrativeCoreGenerator(llm_client=mocker.MagicMock())
    gen._llm.generate.return_value = fake_response

    mini_bio, scenes = gen.generate(_make_persona())

    assert mini_bio.past
    assert mini_bio.present
    assert mini_bio.future
    assert scenes.under_pressure
    assert scenes.friend_recommendation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/generators/test_narrative_core_generator.py::test_generator_returns_mini_biography_and_scene_reactions -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Create `src/aicbc/generators/narrative_core_generator.py`:

```python
"""NarrativeCoreGenerator — produces MiniBiography and SceneReactions from four layers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from aicbc.core.models.persona import (
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
    MiniBiography,
    PersonaProfile,
    SceneReactions,
)
from aicbc.llm.client import LLMClient

logger = structlog.get_logger("aicbc.generators")

DEFAULT_PROMPT_PATH = Path(__file__).parents[2] / "configs" / "prompts" / "narrative_core_generation.txt"

_DEFAULT_MINI_BIO = MiniBiography(
    past="成长过程中的一次具体消费经历塑造了她的价值观。",
    present="在日常工作和家庭责任之间寻找平衡。",
    future="担忧即将到来的大额支出与生活质量之间的冲突。",
)

_DEFAULT_SCENES = SceneReactions(
    under_pressure="压力下会先搜索信息但延迟决策",
    friend_recommendation="会询问细节但保持独立判断",
    flash_sale_limited="容易冲动加购但可能不结算",
    found_cheaper_elsewhere="感到后悔并考虑退换",
    product_fault_after_sales="先查攻略再联系售后",
)


class NarrativeCoreGenerator:
    """Generate the narrative core (mini-biography + scene reactions) for a persona."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        prompt_template_path: Path | str | None = None,
    ) -> None:
        self._llm = llm_client or LLMClient()
        self._prompt_path = Path(prompt_template_path) if prompt_template_path else DEFAULT_PROMPT_PATH
        self._template = self._prompt_path.read_text(encoding="utf-8")

    def generate(self, persona: PersonaProfile) -> tuple[MiniBiography, SceneReactions]:
        """Generate MiniBiography and SceneReactions from the four-layer persona."""
        prompt = self._build_prompt(persona)
        try:
            response = self._llm.generate(
                messages=[
                    {"role": "system", "content": "你是一个资深的消费者研究专家，擅长把标签化画像还原成有故事的人。"},
                    {"role": "user", "content": prompt},
                ],
                json_mode=True,
            )
            parsed = json.loads(response.content)
        except Exception as exc:
            logger.warning("narrative_core_generation_failed", error=str(exc), persona_id=persona.persona_id)
            return _DEFAULT_MINI_BIO, _DEFAULT_SCENES

        mini_bio_data = parsed.get("mini_biography", {})
        mini_bio = MiniBiography(
            past=mini_bio_data.get("past", _DEFAULT_MINI_BIO.past),
            present=mini_bio_data.get("present", _DEFAULT_MINI_BIO.present),
            future=mini_bio_data.get("future", _DEFAULT_MINI_BIO.future),
        )

        scenes_data = parsed.get("scene_reactions", {})
        scenes = SceneReactions(
            under_pressure=scenes_data.get("under_pressure", _DEFAULT_SCENES.under_pressure),
            friend_recommendation=scenes_data.get("friend_recommendation", _DEFAULT_SCENES.friend_recommendation),
            flash_sale_limited=scenes_data.get("flash_sale_limited", _DEFAULT_SCENES.flash_sale_limited),
            found_cheaper_elsewhere=scenes_data.get("found_cheaper_elsewhere", _DEFAULT_SCENES.found_cheaper_elsewhere),
            product_fault_after_sales=scenes_data.get("product_fault_after_sales", _DEFAULT_SCENES.product_fault_after_sales),
        )

        return mini_bio, scenes

    def _build_prompt(self, persona: PersonaProfile) -> str:
        l1 = persona.layer1_demographics
        l2 = persona.layer2_behavior
        l3 = persona.layer3_psychology
        l4 = persona.layer4_scenarios
        tension = l3.tension_combination

        return (
            "基于以下四层消费者画像，生成一段人物小传和五个关键场景反应。\n\n"
            f"人口统计: {l1.age}, {l1.gender}, {l1.city}, {l1.income}, {l1.occupation}, "
            f"{l1.education}, {l1.marital_status}, {l1.living_type}\n"
            f"行为: {l2.decision_style}, 价格敏感度{l2.price_sensitivity}\n"
            f"心理: 价值观{l3.core_values}, 焦虑{l3.core_anxieties}, "
            f"张力[{', '.join(tension.labels)}]: {tension.narrative_explanation}\n"
            f"秘密动机: {l3.secret_motivation}, 防御机制: {l3.defense_mechanism}\n"
            f"情境: {l4.daily_routine}; 触发{l4.purchase_trigger}; 压力{l4.stress_response}\n\n"
            "要求:\n"
            "1. 小传【过去】写一个具体事件，解释当前消费观的来源。\n"
            "2. 小传【现在】描述典型一周的消费节奏。\n"
            "3. 小传【未来】写一个即将到来的转变及其消费含义。\n"
            "4. 场景反应必须是该人物在具体瞬间会怎么做，不要抽象。\n\n"
            "严格返回 JSON，不要 Markdown 代码块:\n"
            '{\n'
            '  "mini_biography": {\n'
            '    "past": "...",\n'
            '    "present": "...",\n'
            '    "future": "..."\n'
            '  },\n'
            '  "scene_reactions": {\n'
            '    "under_pressure": "...",\n'
            '    "friend_recommendation": "...",\n'
            '    "flash_sale_limited": "...",\n'
            '    "found_cheaper_elsewhere": "...",\n'
            '    "product_fault_after_sales": "..."\n'
            '  }\n'
            '}'
        )
```

Create `configs/prompts/narrative_core_generation.txt` with the same prompt text as in `_build_prompt` (for documentation / future extraction):

```text
基于以下四层消费者画像，生成一段人物小传和五个关键场景反应。

人口统计: {{layer1_summary}}
行为: {{decision_style}}, 价格敏感度{{price_sensitivity}}
心理: 价值观{{core_values}}, 焦虑{{core_anxieties}}, 张力[{{tension_labels}}]: {{tension_narrative}}
秘密动机: {{secret_motivation}}, 防御机制: {{defense_mechanism}}
情境: {{daily_routine}}; 触发{{purchase_trigger}}; 压力{{stress_response}}

要求:
1. 小传【过去】写一个具体事件，解释当前消费观的来源。
2. 小传【现在】描述典型一周的消费节奏。
3. 小传【未来】写一个即将到来的转变及其消费含义。
4. 场景反应必须是该人物在具体瞬间会怎么做，不要抽象。

严格返回 JSON，不要 Markdown 代码块:
{
  "mini_biography": {
    "past": "...",
    "present": "...",
    "future": "..."
  },
  "scene_reactions": {
    "under_pressure": "...",
    "friend_recommendation": "...",
    "flash_sale_limited": "...",
    "found_cheaper_elsewhere": "...",
    "product_fault_after_sales": "..."
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/generators/test_narrative_core_generator.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add configs/prompts/narrative_core_generation.txt \
        src/aicbc/generators/narrative_core_generator.py \
        tests/unit/generators/test_narrative_core_generator.py
git commit -m "feat(generators): add NarrativeCoreGenerator"
```

---

## Task 4: NarrativeConsistencyChecker

**Files:**
- Create: `src/aicbc/core/validators/narrative_consistency_checker.py`
- Create: `tests/unit/core/test_narrative_consistency_checker.py`

**Interfaces:**
- Consumes: `PersonaProfile`
- Produces: `NarrativeConsistencyResult`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/core/test_narrative_consistency_checker.py`:

```python
"""Tests for NarrativeConsistencyChecker."""

import pytest

pytestmark = pytest.mark.unit

from aicbc.core.models.persona import (
    DishwasherContext,
    GenerationMetadata,
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
    MiniBiography,
    PersonaProfile,
    SceneReactions,
    TensionCombination,
)
from aicbc.core.validators.narrative_consistency_checker import NarrativeConsistencyChecker


def _make_persona(mini_bio_past: str = "") -> PersonaProfile:
    return PersonaProfile(
        persona_id="persona-test-001",
        segment="测试群体",
        layer1_demographics=Layer1Demographics(
            age="28岁", gender="女", city="新一线城市", income="15-30万元",
            occupation="互联网产品经理", education="本科", marital_status="已婚无孩",
            living_type="自有住房（89㎡）",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="高敏感",
            purchase_channels=["京东"],
            decision_style="参数党",
            brand_loyalty="中等",
            information_source=["知乎"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率"],
            core_anxieties=["时间不够"],
            tension_combination=TensionCombination(
                labels=["高收入", "极简主义"],
                narrative_explanation="她年收入40万却坚持极简生活。",
            ),
            secret_motivation="",
            defense_mechanism="",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="", purchase_trigger="", stress_response="", social_behavior="",
        ),
        mini_biography=MiniBiography(
            past=mini_bio_past or "大学时一次具体事件改变了她的消费观。",
            present="现在经常研究参数再购买。",
            future="未来想减少冲动消费。",
        ),
        scene_reactions=SceneReactions(
            under_pressure="", friend_recommendation="", flash_sale_limited="",
            found_cheaper_elsewhere="", product_fault_after_sales="",
        ),
        language_samples=["a" * 20, "b" * 20, "c" * 20],
        dishwasher_context=DishwasherContext(),
        generation_metadata=GenerationMetadata(),
    )


def test_unexplained_decision_style_is_flagged() -> None:
    """If '参数党' is not explained in the biography, it should be flagged."""
    persona = _make_persona(mini_bio_past="她从小就喜欢买东西，从不研究参数。")
    checker = NarrativeConsistencyChecker()
    result = checker.check(persona)

    assert "参数党" in result.unexplained_tags or result.contradiction_score > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_narrative_consistency_checker.py::test_unexplained_decision_style_is_flagged -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Create `src/aicbc/core/validators/narrative_consistency_checker.py`:

```python
"""NarrativeConsistencyChecker — checks whether the mini-biography explains key tags."""

from __future__ import annotations

from dataclasses import dataclass, field

from aicbc.core.models.persona import PersonaProfile


@dataclass
class NarrativeConsistencyResult:
    """Result of checking narrative-tag consistency."""

    unexplained_tags: list[str] = field(default_factory=list)
    contradiction_score: float = 0.0


class NarrativeConsistencyChecker:
    """Check that key behavioral tags are explained by the mini-biography."""

    def check(self, persona: PersonaProfile) -> NarrativeConsistencyResult:
        """Return tags that appear in layers but lack support in the biography."""
        if not persona.mini_biography:
            return NarrativeConsistencyResult(unexplained_tags=["mini_biography_missing"], contradiction_score=1.0)

        bio_text = " ".join(
            [
                persona.mini_biography.past,
                persona.mini_biography.present,
                persona.mini_biography.future,
            ]
        )

        key_tags: list[str] = []
        l2 = persona.layer2_behavior
        if l2.decision_style:
            key_tags.append(l2.decision_style)
        if l2.price_sensitivity:
            key_tags.append(l2.price_sensitivity)

        l3 = persona.layer3_psychology
        key_tags.extend(l3.tension_combination.labels)

        unexplained: list[str] = []
        for tag in key_tags:
            # Simple substring check; upgrade to embedding similarity in future.
            if tag and tag not in bio_text:
                unexplained.append(tag)

        score = min(1.0, len(unexplained) / max(len(key_tags), 1))
        return NarrativeConsistencyResult(unexplained_tags=unexplained, contradiction_score=round(score, 2))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_narrative_consistency_checker.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/aicbc/core/validators/narrative_consistency_checker.py \
        tests/unit/core/test_narrative_consistency_checker.py
git commit -m "feat(validators): add NarrativeConsistencyChecker"
```

---

## Task 5: LanguageSampleGenerator

**Files:**
- Create: `src/aicbc/generators/language_sample_generator.py`
- Create: `configs/prompts/language_sample_generation.txt`
- Create: `tests/unit/generators/test_language_sample_generator.py`

**Interfaces:**
- Consumes: `PersonaProfile` (with narrative core)
- Produces: `list[str]` of exactly 3 samples

- [ ] **Step 1: Write the failing test**

Create `tests/unit/generators/test_language_sample_generator.py`:

```python
"""Tests for LanguageSampleGenerator."""

import pytest

pytestmark = pytest.mark.unit

from aicbc.core.models.persona import (
    DishwasherContext,
    GenerationMetadata,
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
    MiniBiography,
    PersonaProfile,
    SceneReactions,
    TensionCombination,
)
from aicbc.generators.language_sample_generator import LanguageSampleGenerator


def _make_persona() -> PersonaProfile:
    return PersonaProfile(
        persona_id="persona-test-001",
        segment="测试群体",
        layer1_demographics=Layer1Demographics(
            age="28岁", gender="女", city="新一线城市", income="15-30万元",
            occupation="互联网产品经理", education="本科", marital_status="已婚无孩",
            living_type="自有住房（89㎡）",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="中等敏感",
            purchase_channels=["京东"],
            decision_style="拖延比较型",
            brand_loyalty="中等",
            information_source=["小红书"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率"],
            core_anxieties=["时间不够"],
            tension_combination=TensionCombination(
                labels=["高收入", "极简主义"],
                narrative_explanation="她年收入40万却坚持极简生活。",
            ),
            secret_motivation="",
            defense_mechanism="合理化",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="", purchase_trigger="", stress_response="", social_behavior="",
        ),
        mini_biography=MiniBiography(
            past="大学时跟风买奢侈品导致债务危机。",
            present="现在做攻略再购买。",
            future="未来想减少冲动消费。",
        ),
        scene_reactions=SceneReactions(
            under_pressure="压力大时加购但不结算",
            friend_recommendation="先问缺点",
            flash_sale_limited="设闹钟但常错过",
            found_cheaper_elsewhere="后悔想退换",
            product_fault_after_sales="先查攻略再联系售后",
        ),
        language_samples=["placeholder"] * 3,
        dishwasher_context=DishwasherContext(),
        generation_metadata=GenerationMetadata(),
    )


def test_generator_returns_three_samples(mocker) -> None:
    """Generator should return exactly 3 samples parsed from LLM JSON."""
    fake_response = mocker.MagicMock()
    fake_response.content = (
        '{\n'
        '  "language_samples": [\n'
        '    "洗碗机真的能省时间吗？我没仔细研究过。",\n'
        '    "对比了三个品牌，感觉都差不多，懒得再看了。",\n'
        '    "安装师傅说大概半小时，具体怎么装我也不太清楚。"\n'
        '  ]\n'
        '}'
    )

    gen = LanguageSampleGenerator(llm_client=mocker.MagicMock())
    gen._llm.generate.return_value = fake_response

    samples = gen.generate(_make_persona())

    assert len(samples) == 3
    assert all(20 <= len(s) <= 60 for s in samples)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/generators/test_language_sample_generator.py::test_generator_returns_three_samples -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Create `src/aicbc/generators/language_sample_generator.py`:

```python
"""LanguageSampleGenerator — generates voice-consistent language samples."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from aicbc.core.models.persona import PersonaProfile
from aicbc.llm.client import LLMClient

logger = structlog.get_logger("aicbc.generators")

DEFAULT_PROMPT_PATH = Path(__file__).parents[2] / "configs" / "prompts" / "language_sample_generation.txt"

_DEFAULT_SAMPLES = [
    "洗碗机真的好用吗？我看网上评价褒贬不一，有点纠结。",
    "价格倒是其次，主要是怕买了之后家里老人不会用，放着积灰。",
    "如果真能省出每天洗碗的时间，我觉得多花点钱也值得考虑。",
]


class LanguageSampleGenerator:
    """Generate 3 language samples that sound like the persona."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        prompt_template_path: Path | str | None = None,
    ) -> None:
        self._llm = llm_client or LLMClient()
        self._prompt_path = Path(prompt_template_path) if prompt_template_path else DEFAULT_PROMPT_PATH
        self._template = self._prompt_path.read_text(encoding="utf-8")

    def generate(self, persona: PersonaProfile) -> list[str]:
        """Generate 3 language samples from the persona's narrative core."""
        prompt = self._build_prompt(persona)
        try:
            response = self._llm.generate(
                messages=[
                    {"role": "system", "content": "你是一个消费者研究专家，擅长模仿真实人物的说话方式。"},
                    {"role": "user", "content": prompt},
                ],
                json_mode=True,
            )
            parsed = json.loads(response.content)
        except Exception as exc:
            logger.warning("language_sample_generation_failed", error=str(exc), persona_id=persona.persona_id)
            return list(_DEFAULT_SAMPLES)

        samples = parsed.get("language_samples", [])
        if not isinstance(samples, list) or len(samples) != 3:
            logger.warning("language_sample_count_invalid", count=len(samples) if isinstance(samples, list) else None)
            return list(_DEFAULT_SAMPLES)

        validated: list[str] = []
        for sample in samples:
            if isinstance(sample, str) and 20 <= len(sample.strip()) <= 60:
                validated.append(sample.strip())
            else:
                validated.append(_DEFAULT_SAMPLES[len(validated)])

        return validated

    def _build_prompt(self, persona: PersonaProfile) -> str:
        bio = persona.mini_biography
        scenes = persona.scene_reactions
        l2 = persona.layer2_behavior
        l3 = persona.layer3_psychology

        bio_text = ""
        if bio:
            bio_text = f"过去：{bio.past}\n现在：{bio.present}\n未来：{bio.future}"

        scene_text = ""
        if scenes:
            scene_text = (
                f"压力大时：{scenes.under_pressure}\n"
                f"朋友推荐时：{scenes.friend_recommendation}\n"
                f"大促限时：{scenes.flash_sale_limited}"
            )

        return (
            "请根据以下人物小传和性格，写出 TA 在三个真实瞬间会说的话。\n\n"
            f"决策风格: {l2.decision_style}\n"
            f"防御机制: {l3.defense_mechanism}\n"
            f"小传:\n{bio_text}\n\n"
            f"场景反应:\n{scene_text}\n\n"
            "三个情境:\n"
            "1. 日常聊天中聊到洗碗机\n"
            "2. 评价一款具体洗碗机时\n"
            "3. 被推销员介绍洗碗机时\n\n"
            "要求:\n"
            "- 必须符合 TA 的决策风格和防御机制\n"
            "- 不要刻意堆砌语气词\n"
            "- 不要出现营销术语、完美理性计算、全能专家口吻\n"
            "- 可以暴露知识边界和犹豫\n\n"
            "严格返回 JSON:\n"
            '{\n'
            '  "language_samples": [\n'
            '    "第一条20-60字",\n'
            '    "第二条20-60字",\n'
            '    "第三条20-60字"\n'
            '  ]\n'
            '}'
        )
```

Create `configs/prompts/language_sample_generation.txt` with the same prompt text.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/generators/test_language_sample_generator.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add configs/prompts/language_sample_generation.txt \
        src/aicbc/generators/language_sample_generator.py \
        tests/unit/generators/test_language_sample_generator.py
git commit -m "feat(generators): add LanguageSampleGenerator"
```

---

## Task 6: PersonaProfile schema and ProfileGenerator integration

**Files:**
- Modify: `src/aicbc/core/models/persona.py`
- Modify: `src/aicbc/generators/profile_generator.py`
- Create: `tests/unit/generators/test_profile_generator_realism.py`

**Interfaces:**
- Consumes: `SeedConfig`
- Produces: `PersonaProfile` with `mini_biography`, `scene_reactions`, derived `dishwasher_context`, and validated language samples

- [ ] **Step 1: Write the failing test**

Create `tests/unit/generators/test_profile_generator_realism.py`:

```python
"""Tests for ProfileGenerator realism integration."""

import pytest

pytestmark = pytest.mark.unit

from aicbc.core.models.seed_config import SeedConfig
from aicbc.generators.profile_generator import ProfileGenerator


def test_profile_has_narrative_core_and_derived_context(mocker) -> None:
    """ProfileGenerator should populate mini_biography, scene_reactions, and dishwasher_context."""
    # Mock LLM to return deterministic JSON for each layer + narrative + product + language.
    responses = [
        # Layer 1
        '{"age": "20岁", "gender": "男", "city": "二线城市", "income": "3-8万元", '
        '"occupation": "大学生", "education": "本科", "marital_status": "未婚", "living_type": "学校宿舍"}',
        # Layer 2
        '{"price_sensitivity": "高敏感", "purchase_channels": ["拼多多"], "decision_style": "拖延比较型", '
        '"brand_loyalty": "低", "information_source": ["同学推荐"]}',
        # Layer 3
        '{"core_values": ["省钱"], "core_anxieties": ["同辈压力"], '
        '"tension_combination": {"labels": ["省钱", "想偷懒"], "narrative_explanation": "他生活费有限。"}, '
        '"secret_motivation": "", "defense_mechanism": ""}',
        # Layer 4
        '{"daily_routine": "早8点上课", "purchase_trigger": "", "stress_response": "", "social_behavior": ""}',
        # Narrative core
        '{"mini_biography": {"past": "小学时看到母亲放弃洗碗机", "present": "现在食堂吃饭", "future": "毕业后考虑"}, '
        '"scene_reactions": {"under_pressure": "", "friend_recommendation": "", "flash_sale_limited": "", '
        '"found_cheaper_elsewhere": "", "product_fault_after_sales": ""}}',
        # Product context (should not be reached because dorm short-circuits; kept for completeness)
        '{"eligibility": "not_applicable", "reason": "宿舍", "dishwasher_context": {"purchase_constraints": [], '
        '"decision_factors": [], "ignored_factors": []}}',
        # Language samples
        '{"language_samples": ["洗碗机真的好用吗？我没研究过这些。", "宿舍那么小，装了也没地方放吧。", '
        '"要是毕业后自己租房，我可能会考虑。"]}',
    ]

    mock_llm = mocker.MagicMock()
    mock_response_factory = mocker.MagicMock(side_effect=responses)

    def _fake_generate(*args, **kwargs):
        resp = mocker.MagicMock()
        resp.content = mock_response_factory()
        resp.estimated_cost_usd = 0.0
        resp.model = "mock"
        return resp

    mock_llm.generate.side_effect = _fake_generate

    gen = ProfileGenerator(llm_client=mock_llm)
    seed = SeedConfig(
        life_stage="学生",
        anxieties=["同辈压力"],
        income_bracket="3-8万元",
        city_tier="二线城市",
        tension_score=0.5,
        tension_pairs=[],
        extra_tags={},
    )
    profile = gen.generate("persona-study-0001", seed)

    assert profile.mini_biography is not None
    assert profile.mini_biography.past
    assert profile.scene_reactions is not None
    assert len(profile.language_samples) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/generators/test_profile_generator_realism.py::test_profile_has_narrative_core_and_derived_context -v`

Expected: FAIL (missing attributes or wrong flow).

- [ ] **Step 3: Keep PersonaProfile schema backward-compatible**

Do **not** change `mini_biography`/`scene_reactions` to required fields in this task. Removing `Optional` would break existing tests and fixtures, which requires separate user authorization per `CLAUDE.md`. Instead, ensure the new `ProfileGenerator.generate()` always assigns real values to these fields.

No code change is needed in `src/aicbc/core/models/persona.py` for this task.

Note: A future task can make these fields required after all test fixtures are updated with user authorization.

- [ ] **Step 4: Refactor ProfileGenerator flow**

Modify `src/aicbc/generators/profile_generator.py`:

1. Import new components:

```python
from aicbc.core.validators.narrative_consistency_checker import NarrativeConsistencyChecker
from aicbc.core.validators.plausibility_validator import PlausibilityValidator
from aicbc.core.validators.product_context_deriver import ProductContextDeriver
from aicbc.core.validators.product_context_models import DerivedProductContext
from aicbc.generators.language_sample_generator import LanguageSampleGenerator
from aicbc.generators.narrative_core_generator import NarrativeCoreGenerator
```

2. In `__init__`, instantiate helpers:

```python
self._narrative_gen = NarrativeCoreGenerator(llm_client=self._llm)
self._product_deriver = ProductContextDeriver(llm_client=self._llm)
self._plausibility_validator = PlausibilityValidator()
self._language_gen = LanguageSampleGenerator(llm_client=self._llm)
self._narrative_checker = NarrativeConsistencyChecker()
```

3. Update `generate()` method:

```python
def generate(
    self, persona_id: str, seed_config: SeedConfig, feedback: str | None = None
) -> PersonaProfile:
    log = logger.bind(persona_id=persona_id)
    log.info("profile_generation_start", seed=seed_config.model_dump())

    layer_results: dict[int, dict[str, Any]] = {}
    total_cost_usd = 0.0
    model_used = ""

    for layer_num in range(1, 5):
        layer_feedback = feedback if layer_num == 1 else None
        layer_data, response = self._generate_layer(
            layer_num, seed_config, layer_results, feedback=layer_feedback
        )
        layer_results[layer_num] = layer_data
        if response:
            total_cost_usd += response.estimated_cost_usd
            if not model_used:
                model_used = response.model

    layer1 = Layer1Demographics(**layer_results[1])
    layer2 = Layer2Behavior(**layer_results[2])
    layer3 = Layer3Psychology(**layer_results[3])
    layer4 = Layer4Scenarios(**layer_results[4])

    segment = f"{seed_config.life_stage}-{seed_config.city_tier}"

    # Build a preliminary profile for narrative/core derivation.
    preliminary = PersonaProfile(
        persona_id=persona_id,
        segment=segment,
        layer1_demographics=layer1,
        layer2_behavior=layer2,
        layer3_psychology=layer3,
        layer4_scenarios=layer4,
        language_samples=["placeholder"] * 3,
        dishwasher_context=DishwasherContext(),
        generation_metadata=GenerationMetadata(),
    )

    # Narrative core
    mini_biography, scene_reactions = self._narrative_gen.generate(preliminary)
    preliminary.mini_biography = mini_biography
    preliminary.scene_reactions = scene_reactions

    # Product context derivation
    derived_context = self._product_deriver.derive(preliminary)
    preliminary.dishwasher_context = derived_context.dishwasher_context

    # Plausibility check
    plausibility = self._plausibility_validator.validate(preliminary, derived_context)
    if plausibility.hard_failed:
        log.warning(
            "plausibility_hard_failed",
            findings=[f.rule_id for f in plausibility.findings],
        )
        # We still return the profile; the agent decides whether to regenerate.

    # Language samples from narrative core
    language_samples = self._language_gen.generate(preliminary)

    profile = PersonaProfile(
        persona_id=persona_id,
        segment=segment,
        layer1_demographics=layer1,
        layer2_behavior=layer2,
        layer3_psychology=layer3,
        layer4_scenarios=layer4,
        mini_biography=mini_biography,
        scene_reactions=scene_reactions,
        language_samples=language_samples,
        dishwasher_context=derived_context.dishwasher_context,
        generation_metadata=GenerationMetadata(
            model=model_used or "unknown",
            version="1.0",
            seed=None,
            cost_cny=round(total_cost_usd * 7.2, 4),
        ),
    )

    log.info(
        "profile_generation_complete",
        segment=segment,
        cost_cny=profile.generation_metadata.cost_cny,
    )
    return profile
```

4. Remove or simplify `_generate_auxiliary` since language samples and dishwasher context are now handled separately.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/generators/test_profile_generator_realism.py -v`

Expected: PASS.

- [ ] **Step 6: Run existing ProfileGenerator tests to check regressions**

Run: `uv run pytest tests/unit/generators/test_profile_generator.py -v`

Expected: PASS or identify fixtures that need updating. Do not modify existing tests without user authorization.

- [ ] **Step 7: Commit**

```bash
git add src/aicbc/generators/profile_generator.py \
        tests/unit/generators/test_profile_generator_realism.py
git commit -m "feat(generators): integrate narrative core, product derivation, and plausibility into ProfileGenerator"
```

---

## Task 7: AuthenticityScorer update

**Files:**
- Modify: `src/aicbc/core/scoring/authenticity_scorer.py`
- Create: `tests/unit/business/test_authenticity_scorer_realism.py`

**Interfaces:**
- Consumes: `PersonaProfile` and optional `PlausibilityResult`, `NarrativeConsistencyResult`
- Produces: `AuthenticityResult` with 9 dimensions

- [ ] **Step 1: Write the failing test**

Create `tests/unit/business/test_authenticity_scorer_realism.py`:

```python
"""Tests for AuthenticityScorer realism dimensions."""

import pytest

pytestmark = pytest.mark.unit

from aicbc.core.models.persona import (
    DishwasherContext,
    GenerationMetadata,
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
    MiniBiography,
    PersonaProfile,
    SceneReactions,
    TensionCombination,
)
from aicbc.core.scoring.authenticity_scorer import AuthenticityScorer
from aicbc.core.validators.plausibility_models import PlausibilityFinding, PlausibilityResult
from aicbc.core.validators.narrative_consistency_checker import NarrativeConsistencyResult


def _make_persona() -> PersonaProfile:
    return PersonaProfile(
        persona_id="persona-test-001",
        segment="测试群体",
        layer1_demographics=Layer1Demographics(
            age="28岁", gender="女", city="新一线城市", income="15-30万元",
            occupation="互联网产品经理", education="本科", marital_status="已婚无孩",
            living_type="自有住房（89㎡）",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="中等敏感",
            purchase_channels=["京东"],
            decision_style="理性比较型",
            brand_loyalty="中等",
            information_source=["小红书"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率"],
            core_anxieties=["时间不够"],
            tension_combination=TensionCombination(
                labels=["高收入", "极简主义"],
                narrative_explanation="她年收入40万却坚持极简生活。",
            ),
            secret_motivation="",
            defense_mechanism="",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="早7点起床", purchase_trigger="", stress_response="", social_behavior="",
        ),
        mini_biography=MiniBiography(
            past="具体事件", present="现在状态", future="未来焦虑",
        ),
        scene_reactions=SceneReactions(
            under_pressure="", friend_recommendation="", flash_sale_limited="",
            found_cheaper_elsewhere="", product_fault_after_sales="",
        ),
        language_samples=["a" * 20, "b" * 20, "c" * 20],
        dishwasher_context=DishwasherContext(),
        generation_metadata=GenerationMetadata(),
    )


def test_plausibility_dimension_zero_on_hard_failure() -> None:
    """Plausibility dimension should be 0 when hard rule fails."""
    persona = _make_persona()
    scorer = AuthenticityScorer()
    plausibility = PlausibilityResult(
        passed=False,
        hard_failed=True,
        findings=[PlausibilityFinding(rule_id="PLA-001", severity="hard", message="")],
    )
    result = scorer.score(persona, plausibility_result=plausibility)
    dim = next(d for d in result.dimensions if d.name == "情境合理性")
    assert dim.score == 0


def test_narrative_depth_dimension_two_when_mini_bio_present() -> None:
    """Narrative depth should be 2 when mini-biography has all three parts."""
    persona = _make_persona()
    scorer = AuthenticityScorer()
    result = scorer.score(persona)
    dim = next(d for d in result.dimensions if d.name == "叙事深度")
    assert dim.score == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/business/test_authenticity_scorer_realism.py -v`

Expected: FAIL (`TypeError` for unexpected keyword or missing dimension).

- [ ] **Step 3: Update AuthenticityScorer**

Modify `src/aicbc/core/scoring/authenticity_scorer.py`:

1. Update `score` signature:

```python
def score(
    self,
    persona: PersonaProfile,
    plausibility_result: PlausibilityResult | None = None,
    narrative_consistency_result: NarrativeConsistencyResult | None = None,
) -> AuthenticityResult:
```

2. Add new dimensions:

```python
dimensions.append(self._score_plausibility(persona, plausibility_result))
dimensions.append(self._score_narrative_depth(persona))
```

3. Add `_score_plausibility`:

```python
def _score_plausibility(
    self,
    persona: PersonaProfile,
    plausibility_result: PlausibilityResult | None,
) -> DimensionScore:
    if plausibility_result is None:
        return DimensionScore(name="情境合理性", score=1, rationale="未提供 plausibility 结果")
    if plausibility_result.hard_failed:
        return DimensionScore(
            name="情境合理性",
            score=0,
            rationale=f"hard 规则失败: {', '.join(f.rule_id for f in plausibility_result.findings if f.severity == 'hard')}",
        )
    if plausibility_result.findings:
        return DimensionScore(name="情境合理性", score=1, rationale="存在 soft 提醒")
    return DimensionScore(name="情境合理性", score=2, rationale="情境合理")
```

4. Add `_score_narrative_depth`:

```python
def _score_narrative_depth(self, persona: PersonaProfile) -> DimensionScore:
    bio = persona.mini_biography
    if not bio or not (bio.past and bio.present and bio.future):
        return DimensionScore(name="叙事深度", score=0, rationale="缺少人物小传")
    parts = [bio.past, bio.present, bio.future]
    if all(len(p) >= 10 for p in parts):
        return DimensionScore(name="叙事深度", score=2, rationale="小传包含过去/现在/未来")
    return DimensionScore(name="叙事深度", score=1, rationale="小传存在但部分内容过短")
```

5. Weaken `_score_language_naturalness`: remove the colloquial marker count requirement; keep only jargon penalty and sentence variation as a weak positive.

6. Weaken `_score_social_friction`: lower threshold so that 1 friction marker + defense mechanism yields 2; defense alone yields 1.

- [ ] **Step 4: Run new tests to verify they pass**

Run: `uv run pytest tests/unit/business/test_authenticity_scorer_realism.py -v`

Expected: PASS.

- [ ] **Step 5: Run existing AuthenticityScorer tests**

Run: `uv run pytest tests/unit/business/test_authenticity_scorer.py -v`

Expected: PASS or identify regressions. Do not modify existing tests without user authorization.

- [ ] **Step 6: Commit**

```bash
git add src/aicbc/core/scoring/authenticity_scorer.py \
        tests/unit/business/test_authenticity_scorer_realism.py
git commit -m "feat(scoring): add plausibility and narrative-depth dimensions to AuthenticityScorer"
```

---

## Task 8: ConsumerGeneratorAgent update

**Files:**
- Modify: `src/aicbc/agents/consumer_generator.py`
- Create: `tests/unit/agents/test_consumer_generator_realism.py`

**Interfaces:**
- Consumes: `PlausibilityResult`, `NarrativeConsistencyResult`, `AuthenticityResult`
- Produces: Correction decisions

- [ ] **Step 1: Write the failing test**

Create `tests/unit/agents/test_consumer_generator_realism.py`:

```python
"""Tests for ConsumerGeneratorAgent realism correction logic."""

import pytest

pytestmark = pytest.mark.unit

from aicbc.core.models.persona import (
    DishwasherContext,
    GenerationMetadata,
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
    MiniBiography,
    PersonaProfile,
    SceneReactions,
    TensionCombination,
)
from aicbc.core.validators.plausibility_models import PlausibilityFinding, PlausibilityResult
from aicbc.core.validators.narrative_consistency_checker import NarrativeConsistencyResult
from aicbc.agents.consumer_generator import ConsumerGeneratorAgent


def test_should_correct_triggers_on_hard_plausibility_failure() -> None:
    """Hard plausibility failure must trigger correction."""
    agent = ConsumerGeneratorAgent()
    evaluation = {
        "authenticity_score": 10,
        "authenticity_passed": True,
        "has_tension": True,
        "narrative_ok": True,
        "plausibility_hard_failed": True,
        "plausibility_findings": [PlausibilityFinding(rule_id="PLA-001", severity="hard", message="宿舍")],
        "narrative_under_explained": False,
    }
    should, feedback = agent._should_correct(evaluation)
    assert should is True
    assert "PLA-001" in feedback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_consumer_generator_realism.py::test_should_correct_triggers_on_hard_plausibility_failure -v`

Expected: FAIL (`AssertionError` or missing key).

- [ ] **Step 3: Update ConsumerGeneratorAgent**

Modify `src/aicbc/agents/consumer_generator.py`:

1. Import new validators and deriver:

```python
from aicbc.core.validators.narrative_consistency_checker import NarrativeConsistencyChecker
from aicbc.core.validators.plausibility_validator import PlausibilityValidator
from aicbc.core.validators.product_context_deriver import ProductContextDeriver
from aicbc.core.validators.product_context_models import DerivedProductContext
```

2. In `__init__`, instantiate:

```python
self._product_deriver = ProductContextDeriver()
self._plausibility_validator = PlausibilityValidator()
self._narrative_checker = NarrativeConsistencyChecker()
```

3. Update `_evaluate`:

```python
def _evaluate(self, profile: PersonaProfile) -> dict[str, Any]:
    result = self._scorer.score(profile)

    # Derive product context for plausibility check
    derived_context = self._product_deriver.derive(profile)
    plausibility = self._plausibility_validator.validate(profile, derived_context)

    narrative_check = self._narrative_checker.check(profile)
    bias_result = self._bias_auditor.audit(profile)

    tension_labels = profile.layer3_psychology.tension_combination.labels
    has_tension = len(tension_labels) >= 2

    narrative = profile.layer3_psychology.tension_combination.narrative_explanation
    narrative_ok = len(narrative) >= 50

    return {
        "authenticity_score": result.total_score,
        "authenticity_passed": result.passed,
        "dimensions": [
            {"name": d.name, "score": d.score, "rationale": d.rationale}
            for d in result.dimensions
        ],
        "has_tension": has_tension,
        "narrative_ok": narrative_ok,
        "details": result,
        "bias_status": bias_result.status,
        "bias_high_count": bias_result.high_severity_count,
        "bias_total_findings": len(bias_result.findings),
        "bias_result": bias_result,
        "plausibility_hard_failed": plausibility.hard_failed,
        "plausibility_findings": plausibility.findings,
        "plausibility_passed": plausibility.passed,
        "narrative_under_explained": len(narrative_check.unexplained_tags) >= 2,
        "narrative_unexplained_tags": narrative_check.unexplained_tags,
    }
```

4. Update `_should_correct`:

```python
def _should_correct(self, evaluation: dict[str, Any]) -> tuple[bool, str]:
    # Bias check first
    bias_status = evaluation.get("bias_status", "PENDING")
    bias_high = evaluation.get("bias_high_count", 0)
    if bias_status == "FAILED" or bias_high >= 1:
        bias_findings = evaluation.get("bias_total_findings", 0)
        return True, (
            f"偏见审计未通过(状态={bias_status}, 高危项={bias_high}, "
            f"总发现={bias_findings})—请重新生成并避免刻板印象"
        )

    # Plausibility hard failure
    if evaluation.get("plausibility_hard_failed", False):
        findings = evaluation.get("plausibility_findings", [])
        messages = "; ".join(f"{f.rule_id}: {f.message}" for f in findings if f.severity == "hard")
        return True, f"情境不合理，请修正: {messages}"

    # Narrative under-explained
    if evaluation.get("narrative_under_explained", False):
        tags = evaluation.get("narrative_unexplained_tags", [])
        return True, f"人物小传未能解释以下关键标签: {', '.join(tags)}"

    # Severe authenticity only
    score = evaluation.get("authenticity_score", 0)
    if score < 6:
        return True, f"真实性评分{score}明显偏低，请提升画像真实感"

    if not evaluation.get("has_tension", False):
        return True, "缺少张力组合（矛盾特质）"

    if not evaluation.get("narrative_ok", False):
        return True, "心理叙事解释过短（需≥50字）"

    return False, ""
```

- [ ] **Step 4: Run new test to verify it passes**

Run: `uv run pytest tests/unit/agents/test_consumer_generator_realism.py -v`

Expected: PASS.

- [ ] **Step 5: Run existing agent tests**

Run: `uv run pytest tests/unit/agents/ -v` or the relevant existing test file.

Expected: PASS or identify regressions.

- [ ] **Step 6: Commit**

```bash
git add src/aicbc/agents/consumer_generator.py \
        tests/unit/agents/test_consumer_generator_realism.py
git commit -m "feat(agents): make plausibility and narrative consistency hard gates in ConsumerGeneratorAgent"
```

---

## Task 9: Prompt updates and docs index

**Files:**
- Modify: `configs/prompts/persona_generation.txt`
- Modify: `docs/文档索引与导航.md`

- [ ] **Step 1: Add anti-template constraints to persona generation prompt**

Modify `configs/prompts/persona_generation.txt`: append the following block before the output format section:

```text
【反模板约束】
1. 不得生成“典型都市白领/普通上班族/一般消费者”等无特征描述。
2. 每个人口统计字段必须至少有一个具体细节（如城市不能只说“二线城市”，要说“长沙，租住在老城区单位房”）。
3. 职业必须给出具体行业和一个小习惯（如“做跨境电商运营，习惯用 Excel 记每日支出”）。
4. 必须包含至少一个与人生阶段/收入/城市期待不符的“异常值”，并解释其历史原因。
```

- [ ] **Step 2: Register new docs in the index**

Modify `docs/文档索引与导航.md`: add entries under the appropriate section for:

- `docs/superpowers/specs/2026-06-26-虚拟消费者真实性治理设计.md`
- `docs/superpowers/plans/2026-06-26-virtual-consumer-realism.md`

- [ ] **Step 3: Run a quick generation smoke test (optional, requires LLM key)**

Run: `uv run python -c "from aicbc.agents.consumer_generator import ConsumerGeneratorAgent; agent = ConsumerGeneratorAgent(); p, s = agent.generate_single('smoke', 1); print(p.authenticity_score, p.dishwasher_context)"`

Expected: No exceptions; output shows plausible dishwasher_context for non-student personas.

- [ ] **Step 4: Commit**

```bash
git add configs/prompts/persona_generation.txt docs/文档索引与导航.md
git commit -m "docs(prompts): add anti-template constraints and register realism docs"
```

---

## Task 10: Integration test

**Files:**
- Create: `tests/integration/pipeline/test_realism_governance.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/pipeline/test_realism_governance.py`:

```python
"""Integration test for realism governance end-to-end."""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.not_slow]

from aicbc.core.models.seed_config import SeedConfig
from aicbc.core.validators.plausibility_validator import PlausibilityValidator
from aicbc.core.validators.product_context_deriver import ProductContextDeriver
from aicbc.generators.profile_generator import ProfileGenerator


def test_student_dorm_profile_is_marked_not_applicable(mocker) -> None:
    """A student in a dorm must result in not_applicable dishwasher context."""
    responses = [
        '{"age": "20岁", "gender": "男", "city": "二线城市", "income": "3-8万元", '
        '"occupation": "大学生", "education": "本科", "marital_status": "未婚", "living_type": "学校宿舍"}',
        '{"price_sensitivity": "高敏感", "purchase_channels": ["拼多多"], "decision_style": "拖延比较型", '
        '"brand_loyalty": "低", "information_source": ["同学推荐"]}',
        '{"core_values": ["省钱"], "core_anxieties": ["同辈压力"], '
        '"tension_combination": {"labels": ["省钱", "想偷懒"], "narrative_explanation": "他生活费有限。"}, '
        '"secret_motivation": "", "defense_mechanism": ""}',
        '{"daily_routine": "早8点上课", "purchase_trigger": "", "stress_response": "", "social_behavior": ""}',
        '{"mini_biography": {"past": "小学时看到母亲放弃洗碗机", "present": "现在食堂吃饭", "future": "毕业后考虑"}, '
        '"scene_reactions": {"under_pressure": "", "friend_recommendation": "", "flash_sale_limited": "", '
        '"found_cheaper_elsewhere": "", "product_fault_after_sales": ""}}',
        '{"language_samples": ["洗碗机真的好用吗？我没研究过这些。", "宿舍那么小，装了也没地方放吧。", '
        '"要是毕业后自己租房，我可能会考虑。"]}',
    ]

    mock_llm = mocker.MagicMock()
    call_iter = iter(responses)

    def _fake_generate(*args, **kwargs):
        resp = mocker.MagicMock()
        resp.content = next(call_iter)
        resp.estimated_cost_usd = 0.0
        resp.model = "mock"
        return resp

    mock_llm.generate.side_effect = _fake_generate

    gen = ProfileGenerator(llm_client=mock_llm)
    seed = SeedConfig(
        life_stage="学生",
        anxieties=["同辈压力"],
        income_bracket="3-8万元",
        city_tier="二线城市",
        tension_score=0.5,
        tension_pairs=[],
        extra_tags={},
    )
    profile = gen.generate("persona-integration-0001", seed)

    assert "not_applicable" in profile.dishwasher_context.purchase_constraints[0] or profile.dishwasher_context.purchase_constraints == ["无独立厨房，无法安装"]

    validator = PlausibilityValidator()
    derived = ProductContextDeriver(llm_client=mock_llm).derive(profile)
    result = validator.validate(profile, derived)
    assert result.hard_failed is True
```

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/integration/pipeline/test_realism_governance.py -v`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/pipeline/test_realism_governance.py
git commit -m "test(integration): add realism governance integration test"
```

---

## Self-Review

**Spec coverage:**
- 情境荒诞治理 → Task 1 (PlausibilityValidator), Task 2 (ProductContextDeriver), Task 6 (ProfileGenerator integration), Task 10 (integration test).
- 画像模板化治理 → Task 3 (NarrativeCoreGenerator), Task 4 (NarrativeConsistencyChecker), Task 6 (ProfileGenerator integration), Task 9 (anti-template prompt).
- 语言 AI 感治理 → Task 5 (LanguageSampleGenerator), Task 7 (scorer weakening).
- 评分器重新定位 → Task 7 (add plausibility/narrative dimensions; lower score threshold), Task 8 (correction loop).

**Placeholder scan:**
- No TBD/TODO/fill-in-details.
- All code blocks contain concrete implementations.
- All test commands include expected outputs.

**Type consistency:**
- `PlausibilityResult.hard_failed` used consistently in Task 1, 7, 8.
- `DerivedProductContext.eligibility` literals match across Task 2, 6, 7.
- `MiniBiography` and `SceneReactions` field names match `PersonaProfile` model.

**Known gaps / follow-ups:**
- `PersonaProfile.mini_biography`/`scene_reactions` remain `Optional` in this plan to avoid breaking existing tests and fixtures. Making them truly required requires modifying `tests/conftest.py` and other fixtures, which needs explicit user authorization per `CLAUDE.md`.
- YAML rule engine is intentionally simple (substring matching). More complex rules (price thresholds, semantic matching) can be added later without changing the interface.
- NarrativeConsistencyChecker uses substring matching; upgrade to embedding similarity if needed after baseline metrics are collected.

---

*Plan complete. See execution handoff below.*
