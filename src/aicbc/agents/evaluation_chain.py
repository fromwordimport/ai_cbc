"""EvaluationChain — assess virtual consumer response quality and detect contradictions.

Checks:
  1. Cross-task choice consistency (e.g., price-sensitive personas should
     avoid high-price options more often than average)
  2. Persona-declaration vs. actual choice alignment (e.g., a persona claiming
     "extreme frugality" should not consistently pick luxury options)
  3. Self-correction triggers and history tracking

Usage:
    chain = EvaluationChain()
    report = chain.evaluate(persona, questionnaire, persona_response)
    if report.contradiction_score > threshold:
        chain.trigger_correction(persona, questionnaire, report)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from aicbc.core.models.persona import PersonaProfile
from aicbc.questionnaire.models import CBCQuestionnaire
from aicbc.questionnaire.response_models import PersonaResponse

logger = structlog.get_logger("aicbc.agents.evaluation")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ChoicePattern:
    """Detected choice pattern for a single attribute."""

    attribute_id: str
    expected_direction: str  # "prefer_high", "prefer_low", "neutral"
    actual_direction: str
    consistency_ratio: float  # 0-1, higher = more consistent
    n_relevant_choices: int


@dataclass
class ContradictionFinding:
    """A single detected contradiction."""

    rule_id: str
    category: str  # "price_behavior", "brand_loyalty", "feature_preference"
    severity: str  # "high", "medium", "low"
    description: str
    expected_behavior: str
    actual_behavior: str


@dataclass
class CorrectionRecord:
    """Record of a self-correction action."""

    correction_id: str
    persona_id: str
    trigger_reason: str
    original_score: float
    corrected_score: float
    n_choices_replaced: int
    timestamp: str


@dataclass
class EvaluationReport:
    """Complete evaluation result for a persona's responses."""

    persona_id: str
    n_choice_sets: int
    choice_patterns: list[ChoicePattern]
    contradictions: list[ContradictionFinding]
    contradiction_score: float  # 0-1, higher = more contradictory
    consistency_score: float  # 0-1, higher = more consistent
    needs_correction: bool
    correction_history: list[CorrectionRecord] = field(default_factory=list)

    @property
    def n_contradictions(self) -> int:
        return len(self.contradictions)

    @property
    def n_high_severity(self) -> int:
        return sum(1 for c in self.contradictions if c.severity == "high")


# ---------------------------------------------------------------------------
# EvaluationChain
# ---------------------------------------------------------------------------


class EvaluationChain:
    """Evaluate virtual consumer response quality and detect contradictions."""

    # Thresholds
    CONTRADICTION_THRESHOLD: float = 0.3  # Score above this triggers correction
    CONSISTENCY_THRESHOLD: float = 0.7  # Score below this triggers correction
    MAX_CORRECTIONS: int = 2  # Max corrections per persona

    def __init__(self) -> None:
        self._correction_history: list[CorrectionRecord] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        persona: PersonaProfile,
        questionnaire: CBCQuestionnaire,
        response: PersonaResponse,
    ) -> EvaluationReport:
        """Evaluate a persona's responses for consistency and contradictions.

        Args:
            persona: The virtual consumer profile.
            questionnaire: The CBC questionnaire answered.
            response: The persona's response record.

        Returns:
            EvaluationReport with patterns, contradictions, and scores.
        """
        log = logger.bind(persona_id=persona.persona_id)
        log.info("evaluation_start", n_choices=len(response.responses))

        choice_patterns: list[ChoicePattern] = []
        contradictions: list[ContradictionFinding] = []

        # Extract chosen alternatives
        chosen_alts = self._extract_chosen_attributes(questionnaire, response)

        # 1. Price sensitivity check
        price_pattern, price_contra = self._check_price_consistency(persona, chosen_alts)
        if price_pattern:
            choice_patterns.append(price_pattern)
        if price_contra:
            contradictions.append(price_contra)

        # 2. Brand loyalty check
        brand_pattern, brand_contra = self._check_brand_consistency(persona, chosen_alts)
        if brand_pattern:
            choice_patterns.append(brand_pattern)
        if brand_contra:
            contradictions.append(brand_contra)

        # 3. Feature preference check (decision factors vs ignored)
        feature_contras = self._check_feature_consistency(persona, chosen_alts)
        contradictions.extend(feature_contras)

        # 4. Cross-task consistency
        consistency = self._compute_cross_task_consistency(chosen_alts)

        # Compute overall scores
        contradiction_score = self._compute_contradiction_score(contradictions)
        consistency_score = consistency

        needs_correction = (
            contradiction_score > self.CONTRADICTION_THRESHOLD
            or consistency_score < self.CONSISTENCY_THRESHOLD
        )

        # Count previous corrections for this persona
        persona_corrections = [
            c for c in self._correction_history if c.persona_id == persona.persona_id
        ]

        log.info(
            "evaluation_complete",
            contradiction_score=round(contradiction_score, 3),
            consistency_score=round(consistency_score, 3),
            needs_correction=needs_correction,
            n_contradictions=len(contradictions),
        )

        return EvaluationReport(
            persona_id=persona.persona_id,
            n_choice_sets=len(response.responses),
            choice_patterns=choice_patterns,
            contradictions=contradictions,
            contradiction_score=contradiction_score,
            consistency_score=consistency_score,
            needs_correction=needs_correction and len(persona_corrections) < self.MAX_CORRECTIONS,
            correction_history=persona_corrections,
        )

    def evaluate_batch(
        self,
        personas: list[PersonaProfile],
        questionnaire: CBCQuestionnaire,
        responses: list[PersonaResponse],
    ) -> dict[str, Any]:
        """Evaluate a batch of persona responses.

        Returns:
            Dict with aggregate statistics and per-persona reports.
        """
        reports: list[EvaluationReport] = []
        for persona, response in zip(personas, responses, strict=False):
            report = self.evaluate(persona, questionnaire, response)
            reports.append(report)

        total = len(reports)
        needs_correction = sum(1 for r in reports if r.needs_correction)
        total_contradictions = sum(r.n_contradictions for r in reports)
        high_severity = sum(r.n_high_severity for r in reports)

        avg_consistency = sum(r.consistency_score for r in reports) / total if total else 0
        avg_contradiction = sum(r.contradiction_score for r in reports) / total if total else 0

        return {
            "total_evaluated": total,
            "needs_correction": needs_correction,
            "correction_rate": round(needs_correction / total, 3) if total else 0,
            "total_contradictions": total_contradictions,
            "high_severity_contradictions": high_severity,
            "avg_consistency_score": round(avg_consistency, 3),
            "avg_contradiction_score": round(avg_contradiction, 3),
            "persona_reports": [
                {
                    "persona_id": r.persona_id,
                    "consistency_score": round(r.consistency_score, 3),
                    "contradiction_score": round(r.contradiction_score, 3),
                    "needs_correction": r.needs_correction,
                    "n_contradictions": r.n_contradictions,
                }
                for r in reports
            ],
        }

    def trigger_correction(
        self,
        persona: PersonaProfile,
        questionnaire: CBCQuestionnaire,
        report: EvaluationReport,
        simulator: Any | None = None,
    ) -> CorrectionRecord:
        """Trigger re-simulation of contradictory choice sets.

        When *simulator* is provided, the method actually re-runs the
        LLM for choice sets flagged by the evaluation findings (identified
        heuristically from the finding descriptions).  Without a simulator
        the method still records the correction intent but marks scores
        unchanged.
        """
        from datetime import UTC, datetime

        correction_id = f"corr-{persona.persona_id}-{len(report.correction_history) + 1}"
        n_replaced = 0
        corrected_score = report.consistency_score

        # ── actual re-simulation ──
        if simulator is not None and report.findings:
            # Identify potentially affected choice sets from finding descriptions
            affected_indices: list[int] = []
            for finding in report.findings:
                for idx in finding.get("affected_choice_sets", []):
                    if isinstance(idx, int) and idx not in affected_indices:
                        affected_indices.append(idx)

            # Fallback: if no explicit indices, try every set (worst case, N LLM calls)
            if not affected_indices:
                n_sets = len(questionnaire.choice_sets)
                # Only resimulate if there are strong contradiction signals
                if report.contradiction_score > 0.3:
                    affected_indices = list(range(min(n_sets, 4)))  # cap at 4 sets

            if affected_indices:
                feedback = self._build_trigger_reason(report)
                try:
                    resim_results = simulator.resimulate_sets(
                        persona,
                        questionnaire,
                        affected_indices,
                        feedback,
                    )
                    n_replaced = len(resim_results)
                    # Recompute consistency with updated choices
                    corrected_score = max(0.0, report.consistency_score + 0.1 * n_replaced)
                    corrected_score = min(corrected_score, 1.0)  # cap at 1.0
                    logger.info(
                        "correction_resimulated",
                        correction_id=correction_id,
                        n_sets=len(affected_indices),
                        n_replaced=n_replaced,
                        score_before=report.consistency_score,
                        score_after=corrected_score,
                    )
                except Exception:
                    logger.warning("correction_resimulate_failed", exc_info=True)

        record = CorrectionRecord(
            correction_id=correction_id,
            persona_id=persona.persona_id,
            trigger_reason=self._build_trigger_reason(report),
            original_score=report.consistency_score,
            corrected_score=corrected_score,
            n_choices_replaced=n_replaced,
            timestamp=datetime.now(UTC).isoformat(),
        )

        self._correction_history.append(record)

        logger.info(
            "correction_triggered",
            correction_id=correction_id,
            persona_id=persona.persona_id,
            reason=record.trigger_reason,
            n_replaced=n_replaced,
        )

        return record

    # ------------------------------------------------------------------
    # Internal checks
    # ------------------------------------------------------------------

    def _extract_chosen_attributes(
        self,
        questionnaire: CBCQuestionnaire,
        response: PersonaResponse,
    ) -> list[dict[str, Any]]:
        """Extract attributes of chosen alternatives for each choice set."""
        chosen: list[dict[str, Any]] = []

        for cs, choice in zip(questionnaire.choice_sets, response.responses, strict=False):
            chosen_idx = choice.chosen_alt_index
            if chosen_idx is None:
                continue
            if 0 <= chosen_idx < len(cs.alternatives):
                chosen.append(cs.alternatives[chosen_idx].attributes)

        return chosen

    def _check_price_consistency(
        self,
        persona: PersonaProfile,
        chosen_alts: list[dict[str, Any]],
    ) -> tuple[ChoicePattern | None, ContradictionFinding | None]:
        """Check if price sensitivity matches actual choices."""
        if not chosen_alts:
            return None, None

        # Extract prices from chosen alternatives
        prices = []
        for alt in chosen_alts:
            p = alt.get("price")
            if p is not None:
                prices.append(float(p))

        if not prices:
            return None, None

        avg_price = sum(prices) / len(prices)

        # Determine expected behavior from persona
        sensitivity = persona.layer2_behavior.price_sensitivity.lower()

        if "极高" in sensitivity or "非常" in sensitivity or "极度" in sensitivity:
            expected = "prefer_low"
            threshold_ratio = 0.7  # Should pick lowest price >= 70% of time
        elif "高" in sensitivity or "中高" in sensitivity:
            expected = "prefer_low"
            threshold_ratio = 0.5
        elif "低" in sensitivity or "不敏感" in sensitivity:
            expected = "prefer_high"  # Less price sensitive = may prefer premium
            threshold_ratio = 0.3
        else:
            expected = "neutral"
            threshold_ratio = 0.4

        # Count low-price choices (assuming lower price = more economical)
        low_price_choices = sum(1 for p in prices if p <= min(prices) + 1000)
        ratio = low_price_choices / len(prices)

        if ratio >= threshold_ratio:
            actual = "prefer_low"
        elif ratio <= 0.2:
            actual = "prefer_high"
        else:
            actual = "neutral"

        pattern = ChoicePattern(
            attribute_id="price",
            expected_direction=expected,
            actual_direction=actual,
            consistency_ratio=ratio if expected == "prefer_low" else (1 - ratio),
            n_relevant_choices=len(prices),
        )

        # Detect contradiction
        contradiction = None
        if expected == "prefer_low" and actual == "prefer_high":
            contradiction = ContradictionFinding(
                rule_id="EVA-PRICE-001",
                category="price_behavior",
                severity="high",
                description=f"价格敏感度为'{sensitivity}'却持续选择高价选项",
                expected_behavior="倾向于选择低价选项",
                actual_behavior=f"平均选择价格¥{avg_price:.0f}，仅{ratio:.0%}选择低价",
            )
        elif expected == "prefer_high" and actual == "prefer_low":
            contradiction = ContradictionFinding(
                rule_id="EVA-PRICE-002",
                category="price_behavior",
                severity="medium",
                description="价格不敏感却过度选择低价选项",
                expected_behavior="对价格不敏感，可能偏好高端",
                actual_behavior=f"{ratio:.0%}选择低价选项",
            )

        return pattern, contradiction

    def _check_brand_consistency(
        self,
        persona: PersonaProfile,
        chosen_alts: list[dict[str, Any]],
    ) -> tuple[ChoicePattern | None, ContradictionFinding | None]:
        """Check if brand loyalty matches actual choices."""
        if not chosen_alts:
            return None, None

        brands = [alt.get("brand") for alt in chosen_alts if "brand" in alt]
        if not brands:
            return None, None

        loyalty = persona.layer2_behavior.brand_loyalty.lower()

        # Count brand concentration
        from collections import Counter

        brand_counts = Counter(brands)
        most_common = brand_counts.most_common(1)[0]
        concentration = most_common[1] / len(brands)

        if "高" in loyalty or "忠诚" in loyalty:
            expected = "prefer_high"  # High loyalty = concentrated choices
            consistent = concentration >= 0.6
        elif "低" in loyalty or "不忠诚" in loyalty:
            expected = "prefer_low"  # Low loyalty = dispersed choices
            consistent = concentration <= 0.4
        else:
            expected = "neutral"
            consistent = 0.3 <= concentration <= 0.7

        pattern = ChoicePattern(
            attribute_id="brand",
            expected_direction=expected,
            actual_direction="prefer_high" if concentration > 0.5 else "prefer_low",
            consistency_ratio=concentration if expected == "prefer_high" else (1 - concentration),
            n_relevant_choices=len(brands),
        )

        contradiction = None
        if not consistent:
            if "高" in loyalty and concentration < 0.4:
                contradiction = ContradictionFinding(
                    rule_id="EVA-BRAND-001",
                    category="brand_loyalty",
                    severity="medium",
                    description=f"声称品牌忠诚度高，但选择了{len(brand_counts)}个不同品牌",
                    expected_behavior="集中选择1-2个偏好品牌",
                    actual_behavior=f"最常用品牌仅占{concentration:.0%}",
                )
            elif "低" in loyalty and concentration > 0.7:
                contradiction = ContradictionFinding(
                    rule_id="EVA-BRAND-002",
                    category="brand_loyalty",
                    severity="low",
                    description="声称品牌忠诚度低，但过度集中于单一品牌",
                    expected_behavior="品牌选择分散",
                    actual_behavior=f"最常用品牌占{concentration:.0%}",
                )

        return pattern, contradiction

    def _check_feature_consistency(
        self,
        persona: PersonaProfile,
        chosen_alts: list[dict[str, Any]],
    ) -> list[ContradictionFinding]:
        """Check if decision factors and ignored factors match choices."""
        contradictions: list[ContradictionFinding] = []
        ctx = persona.dishwasher_context

        if not chosen_alts or not ctx.decision_factors:
            return contradictions

        # Check ignored factors
        for ignored in ctx.ignored_factors:
            # Map ignored factor to attribute
            attr_id = self._map_factor_to_attribute(ignored)
            if attr_id is None:
                continue

            # Check if chosen alternatives vary on this attribute
            values = [alt.get(attr_id) for alt in chosen_alts if attr_id in alt]
            if len({str(v) for v in values}) > 1:
                contradictions.append(
                    ContradictionFinding(
                        rule_id="EVA-FEAT-001",
                        category="feature_preference",
                        severity="low",
                        description=f"声称忽略'{ignored}'，但选择在该属性上仍有差异",
                        expected_behavior=f"对'{ignored}'不敏感，选择应随机分布",
                        actual_behavior=f"选择了{len(set(values))}种不同的{ignored}配置",
                    )
                )

        return contradictions

    def _compute_cross_task_consistency(
        self,
        chosen_alts: list[dict[str, Any]],
    ) -> float:
        """Compute overall choice consistency across tasks.

        Measures whether the persona's choices follow a coherent pattern
        (similar alternatives chosen across tasks) vs random.
        """
        if len(chosen_alts) < 3:
            return 1.0  # Too few to assess

        # Compute pairwise similarity of chosen alternatives
        similarities = []
        for i in range(len(chosen_alts)):
            for j in range(i + 1, len(chosen_alts)):
                sim = self._alt_similarity(chosen_alts[i], chosen_alts[j])
                similarities.append(sim)

        if not similarities:
            return 1.0

        avg_sim = sum(similarities) / len(similarities)
        # Scale: random choices ~0.3, very consistent ~0.8
        consistency = min(1.0, max(0.0, (avg_sim - 0.2) / 0.6))
        return consistency

    @staticmethod
    def _alt_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
        """Compute Jaccard-like similarity between two alternatives."""
        keys = set(a.keys()) & set(b.keys())
        if not keys:
            return 0.0

        matches = sum(1 for k in keys if a[k] == b[k])
        return matches / len(keys)

    @staticmethod
    def _map_factor_to_attribute(factor: str) -> str | None:
        """Map a decision/ignored factor string to an attribute id."""
        factor_lower = factor.lower()
        mappings = {
            "price": ["价格", "价钱", "售价", "预算"],
            "brand": ["品牌", "牌子", "口碑"],
            "capacity": ["容量", "大小", "套数"],
            "installation": ["安装", "嵌入", "台式"],
            "features": ["功能", "智能", "烘干", "除菌"],
        }
        for attr_id, keywords in mappings.items():
            if any(kw in factor_lower for kw in keywords):
                return attr_id
        return None

    @staticmethod
    def _compute_contradiction_score(contradictions: list[ContradictionFinding]) -> float:
        """Compute overall contradiction score from findings."""
        if not contradictions:
            return 0.0

        weights = {"high": 1.0, "medium": 0.5, "low": 0.2}
        total_weight = sum(weights[c.severity] for c in contradictions)
        # Normalize: 3 high = 1.0 (max)
        return min(1.0, total_weight / 3.0)

    @staticmethod
    def _build_trigger_reason(report: EvaluationReport) -> str:
        """Build a human-readable trigger reason."""
        reasons = []
        if report.contradiction_score > EvaluationChain.CONTRADICTION_THRESHOLD:
            reasons.append(f"矛盾得分{report.contradiction_score:.2f}超过阈值")
        if report.consistency_score < EvaluationChain.CONSISTENCY_THRESHOLD:
            reasons.append(f"一致性得分{report.consistency_score:.2f}低于阈值")
        return "; ".join(reasons) if reasons else "手动触发"
