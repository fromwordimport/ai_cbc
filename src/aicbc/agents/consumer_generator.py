"""ConsumerGeneratorAgent — generates virtual consumer personas with self-correction.

Encapsulates ProfileGenerator, AuthenticityScorer, and BiasAuditor as tools,
providing a unified agent interface with three-layer prompts and evaluation chains.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aicbc.agents.base import (
    AgentState,
    BaseAgent,
    DynamicExample,
    RuleInjection,
    SystemInstruction,
    ToolSpec,
)
from aicbc.core.models.persona import PersonaProfile
from aicbc.core.scoring.authenticity_scorer import AuthenticityScorer
from aicbc.core.scoring.bias_auditor import BiasAuditor
from aicbc.generators.profile_generator import ProfileGenerator
from aicbc.generators.seed_generator import SeedGenerator


class ConsumerGeneratorAgent(BaseAgent[PersonaProfile]):
    """Agent that generates four-layer consumer personas with quality assurance.

    Workflow:
        1. Generate seed config (tags + tensions)
        2. Generate four-layer persona via ProfileGenerator tool
        3. Score authenticity via AuthenticityScorer tool
        4. If score < threshold, trigger self-correction with feedback
        5. Return final persona + generation state

    The agent enforces:
        - Tension-first: every persona must have internally contradictory traits
        - Four-layer coherence: upper layers explain lower-layer anomalies
        - Authenticity threshold: score >= 9 (configurable)
    """

    DEFAULT_AUTHENTICITY_THRESHOLD = 9.0

    def __init__(
        self,
        profile_generator: ProfileGenerator | None = None,
        seed_generator: SeedGenerator | None = None,
        authenticity_threshold: float = DEFAULT_AUTHENTICITY_THRESHOLD,
        max_corrections: int = 3,
    ) -> None:
        system = SystemInstruction(
            role="虚拟消费者生成专家",
            expertise=[
                "消费者心理学",
                "人格建模",
                "矛盾张力设计",
                "Choice-Based Conjoint研究",
            ],
            constraints=[
                "生成的消费者必须有内在矛盾，不能是'平均人'",
                "每个矛盾必须有心理叙事解释",
                "上层特征必须能解释下层异常",
            ],
        )

        rules = RuleInjection(
            rules=[
                "每个消费者画像必须包含至少一组张力标签（矛盾特质）",
                "张力组合的心理叙事解释不少于50字",
                "语言样本必须体现口语化特征，禁止营销术语",
                "决策风格不能声称对所有维度进行精确计算",
                "必须承认知识边界，不能声称了解所有品牌/参数",
                # 公平性硬规则 (RULE-FAIR-001 ~ RULE-FAIR-006)
                "RULE-FAIR-001：禁止将性别与消费决策能力建立因果关联",
                "RULE-FAIR-002：禁止将地域/城市等级与消费能力简单绑定",
                "RULE-FAIR-003：禁止将年龄与科技接受度反向关联",
                "RULE-FAIR-004：禁止将职业与社会阶层/消费品位绑定",
                "RULE-FAIR-005：禁止将收入与价格敏感度线性关联",
                "RULE-FAIR-006：禁止将婚姻状况与家庭决策角色刻板分配",
            ],
            forbidden_patterns=[
                "营销术语：性价比、用户体验、痛点、场景化、赋能",
                "过度理性行为：计算NPV、Excel比价、全平台统计",
                "完美人设：无矛盾、无焦虑、所有决策都正确",
                # 公平性相关的刻板表达
                "性别刻板：男性只看参数/女性只看外观",
                "地域刻板：低线城市等于低收入/低教育",
                "年龄刻板：老年人不会用智能产品",
                "职业刻板：蓝领没有生活品质追求",
                "收入刻板：高收入一定不在乎价格",
                "婚姻刻板：已婚女性只为家庭消费/未婚者只顾自己",
            ],
            required_fields=[
                "layer1_demographics: 8个人口统计字段",
                "layer2_behavior: 5个行为字段",
                "layer3_psychology: 张力组合+心理叙事",
                "layer4_scenarios: 4个情境字段",
                "language_samples: 3条20-60字发言",
            ],
        )

        examples = [
            DynamicExample(
                input_context="人生阶段：精致白领，一线城市，年收入25-40万",
                expected_output=(
                    "张力组合：['高收入', '极简主义']\n"
                    "叙事：她年收入35万却坚持极简生活，源于童年物质匮乏的记忆..."
                ),
                rationale="高收入与极简主义的矛盾需要深层心理解释",
            ),
        ]

        super().__init__(
            system_instruction=system,
            rules=rules,
            examples=examples,
            max_corrections=max_corrections,
        )

        self._profile_gen = profile_generator or ProfileGenerator()
        self._seed_gen = seed_generator or SeedGenerator()
        self._scorer = AuthenticityScorer()
        self._bias_auditor = BiasAuditor()  # Task 3: bias-driven self-correction
        self._threshold = authenticity_threshold

        # Register tools with permission tags (SEC-009)
        self.register_tool(
            "generate_seed",
            self._seed_gen.generate_seed,
            ToolSpec(
                name="generate_seed",
                description="Generate a seed config from tag combinations",
                parameters={"life_stage": "str", "anxieties": "list[str]"},
                permission_tags=["generation"],
            ),
        )
        self.register_tool(
            "generate_profile",
            self._profile_gen.generate,
            ToolSpec(
                name="generate_profile",
                description="Generate a four-layer persona from seed config",
                parameters={"persona_id": "str", "seed_config": "SeedConfig"},
                permission_tags=["generation"],
            ),
        )
        self.register_tool(
            "score_authenticity",
            self._scorer.score,
            ToolSpec(
                name="score_authenticity",
                description="Score persona authenticity (0-14)",
                parameters={"persona": "PersonaProfile"},
                permission_tags=["scoring"],
            ),
        )

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def execute(
        self,
        study_id: str,
        index: int,
        life_stage: str | None = None,
        anxieties: list[str] | None = None,
        seed: int | None = None,
        feedback: str = "",
    ) -> PersonaProfile:
        """Generate a single persona with optional correction feedback.

        Args:
            study_id: Parent study identifier.
            index: Persona index for ID generation.
            life_stage: Optional life stage override.
            anxieties: Optional anxiety tags override.
            seed: Optional random seed.
            feedback: Correction feedback from previous attempt (if any).

        Returns:
            Generated PersonaProfile.
        """
        persona_id = f"persona-{study_id}-{index:04d}"
        log = self._log.bind(persona_id=persona_id)

        # Generate seed config
        seed_config = self.call_tool(
            "generate_seed",
            life_stage=life_stage,
            anxieties=anxieties,
            seed=seed,
        )

        # If feedback exists, inject it into the generation context
        if feedback:
            log.info("generation_with_feedback", feedback_preview=feedback[:100])

        # Generate profile — pass feedback for correction-aware regeneration
        profile = self.call_tool(
            "generate_profile",
            persona_id=persona_id,
            seed_config=seed_config,
            feedback=feedback,
        )

        log.info(
            "persona_generated",
            segment=profile.segment,
            cost_cny=profile.generation_metadata.cost_cny,
        )
        return profile

    def generate_single(
        self,
        study_id: str,
        index: int,
        life_stage: str | None = None,
        anxieties: list[str] | None = None,
        seed: int | None = None,
    ) -> tuple[PersonaProfile, AgentState]:
        """Generate a persona with full evaluation and self-correction loop.

        This is the primary public API for single persona generation.

        Returns:
            Tuple of (final_persona, agent_state).
        """
        result, state = self.run_with_correction(
            execute_fn=self.execute,
            evaluate_fn=self._evaluate,
            study_id=study_id,
            index=index,
            life_stage=life_stage,
            anxieties=anxieties,
            seed=seed,
        )

        # Attach final authenticity score to profile
        if isinstance(result, PersonaProfile):
            final_score = self._scorer.score(result)
            result.authenticity_score = final_score.total_score

        return result, state

    def generate_batch(
        self,
        study_id: str,
        count: int,
        life_stages: list[str] | None = None,
        seed: int | None = None,
        max_concurrency: int = 3,
    ) -> tuple[list[PersonaProfile], list[AgentState], dict[str, Any]]:
        """Generate a batch of personas concurrently with error isolation.

        Uses ``asyncio.Semaphore`` to cap parallel LLM calls and avoid
        triggering provider rate limits.  Individual persona failures are
        logged but do not abort the batch; failed items are excluded from
        the returned lists while successful results preserve their original
        index order.

        Args:
            study_id: Parent study identifier.
            count: Number of personas to generate.
            life_stages: Optional list of life stages (rotated if fewer than count).
            seed: Optional base random seed.
            max_concurrency: Max simultaneous persona generations (default 3).

        Returns:
            Tuple of (profiles, states, summary).  ``profiles`` and ``states``
            are aligned one-to-one and contain only successful generations.
        """

        async def _batch_core() -> list:
            semaphore = asyncio.Semaphore(max_concurrency)

            async def _bounded_generate(index: int):
                async with semaphore:
                    # Run the synchronous generate_single in a thread so the
                    # event loop stays responsive.
                    return index, await asyncio.to_thread(
                        self.generate_single,
                        study_id=study_id,
                        index=index,
                        life_stage=life_stages[index % len(life_stages)] if life_stages else None,
                        seed=(seed + index) if seed is not None else None,
                    )

            tasks = [_bounded_generate(i) for i in range(count)]
            # return_exceptions=True : errors are returned as Exception objects
            # rather than aborting the entire gather.
            return list(await asyncio.gather(*tasks, return_exceptions=True))

        raw_results = asyncio.run(_batch_core())

        # Reassemble results in original index order, skipping failures
        profiles: list[PersonaProfile] = []
        states: list[AgentState] = []
        failures: list[dict[str, Any]] = []
        total_corrections = 0
        passed_count = 0

        # Sort by index to guarantee original order (gather preserves creation
        # order but explicit sort is defensive).
        indexed: list[tuple[int, Any]] = []
        for item in raw_results:
            if isinstance(item, Exception):
                self._log.error(
                    "batch_gather_unexpected_failure",
                    error_type=type(item).__name__,
                    error=str(item),
                )
                continue
            indexed.append(item)
        indexed.sort(key=lambda x: x[0])

        for index, payload in indexed:
            if isinstance(payload, Exception):
                self._log.error(
                    "batch_persona_failed",
                    index=index,
                    error_type=type(payload).__name__,
                    error=str(payload),
                )
                failures.append({"index": index, "error": str(payload)[:200]})
                continue

            profile, state = payload
            profiles.append(profile)
            states.append(state)
            total_corrections += state.correction_count
            if (
                profile.authenticity_score is not None
                and profile.authenticity_score >= self._threshold
            ):
                passed_count += 1

        generated_count = len(profiles)
        failed_count = len(failures)

        summary = {
            "requested": count,
            "generated": generated_count,
            "failed": failed_count,
            "passed_authenticity": passed_count,
            "failed_authenticity": generated_count - passed_count,
            "total_corrections": total_corrections,
            "avg_authenticity_score": sum(p.authenticity_score or 0 for p in profiles)
            / max(generated_count, 1),
            "concurrency": max_concurrency,
            "failures": failures,
        }

        self._log.info("batch_generation_complete", **summary)
        return profiles, states, summary

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def _evaluate(self, profile: PersonaProfile) -> dict[str, Any]:
        """Evaluate a generated persona and return assessment dict."""
        result = self._scorer.score(profile)

        # Bias audit (Task 3)
        bias_result = self._bias_auditor.audit(profile)

        # Check tension presence
        tension_labels = profile.layer3_psychology.tension_combination.labels
        has_tension = len(tension_labels) >= 2

        # Check narrative length
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
        }

    def _should_correct(self, evaluation: dict[str, Any]) -> tuple[bool, str]:
        """Determine if self-correction is needed.

        Returns (should_correct: bool, feedback: str).

        Triggers re-generation on:
          - Authenticity score below threshold
          - Missing tension combination
          - Narrative too short
          - CRITICAL bias status (FAILED) or >=1 HIGH bias finding
        """
        # Bias check first (most important — biased output must be re-generated)
        bias_status = evaluation.get("bias_status", "PENDING")
        bias_high = evaluation.get("bias_high_count", 0)
        if bias_status == "FAILED" or bias_high >= 1:
            bias_findings = evaluation.get("bias_total_findings", 0)
            return True, (
                f"偏见审计未通过(状态={bias_status}, 高危项={bias_high}, "
                f"总发现={bias_findings})—请重新生成并避免刻板印象"
            )

        score = evaluation.get("authenticity_score", 0)
        if score < self._threshold:
            return True, f"真实性评分{score}低于阈值{self._threshold}"

        if not evaluation.get("has_tension", False):
            return True, "缺少张力组合（矛盾特质）"

        if not evaluation.get("narrative_ok", False):
            return True, "心理叙事解释过短（需≥50字）"

        return False, ""
