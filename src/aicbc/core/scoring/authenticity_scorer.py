"""AuthenticityScorer — rule-based evaluation of persona realism.

Scores across 7 dimensions (0-2 each), total 0-14.
    >= 12: Excellent
    >= 9:  Pass
    < 9:   Needs revision
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from aicbc.core.models.persona import PersonaProfile

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class DimensionScore:
    """Score for a single authenticity dimension."""

    name: str
    score: int  # 0, 1, or 2
    max_score: int = 2
    rationale: str = ""


@dataclass
class AuthenticityResult:
    """Complete authenticity scoring result."""

    total_score: float
    max_score: float = 14.0
    dimensions: list[DimensionScore] = field(default_factory=list)
    passed: bool = False

    @property
    def grade(self) -> str:
        if self.total_score >= 12:
            return "优秀"
        if self.total_score >= 9:
            return "良好"
        if self.total_score >= 6:
            return "一般"
        return "不合格"


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class AuthenticityScorer:
    """Evaluate persona realism via 7 rule-based dimensions.

    Each dimension scores 0-2:
      0 = severely unrealistic
      1 = partially realistic but with idealisation traces
      2 = highly realistic with visible internal contradictions
    """

    # Marketing / academic jargon that real consumers rarely use
    MARKETING_TERMS: set[str] = {
        "性价比",
        "用户体验",
        "痛点",
        "场景化",
        "垂直领域",
        "私域流量",
        "公域流量",
        "转化漏斗",
        "用户画像",
        "底层逻辑",
        "顶层设计",
        "组合拳",
        "闭环",
        "抓手",
        "赋能",
        "对齐",
        "颗粒度",
        "调性",
        "打法",
    }

    # Overly rational / perfect behaviours
    PERFECT_RATIONALITY_PATTERNS: list[str] = [
        r"计算.*NPV",
        r"Excel.*比价",
        r"全平台.*统计",
        r"精确到小数点后",
        r"制作.*对比表",
        r"量化.*分析",
    ]

    def score(self, persona: PersonaProfile) -> AuthenticityResult:
        """Run all 7 dimensions and return aggregated result."""
        dimensions: list[DimensionScore] = []

        dimensions.append(self._score_internal_consistency(persona))
        dimensions.append(self._score_situational_sensitivity(persona))
        dimensions.append(self._score_cognitive_limitation(persona))
        dimensions.append(self._score_social_friction(persona))
        dimensions.append(self._score_temporal_continuity(persona))
        dimensions.append(self._score_language_naturalness(persona))
        dimensions.append(self._score_knowledge_boundary(persona))

        total = sum(d.score for d in dimensions)
        return AuthenticityResult(
            total_score=total,
            dimensions=dimensions,
            passed=total >= 9,
        )

    # ------------------------------------------------------------------
    # Dimension 1: Internal Consistency
    # ------------------------------------------------------------------

    def _score_internal_consistency(self, persona: PersonaProfile) -> DimensionScore:
        """Behaviours must be explainable by psychological motives.

        Checks: Does tension narrative actually explain the contradiction?
        Do stated values align with behaviour patterns?
        """
        l3 = persona.layer3_psychology

        tension = l3.tension_combination
        narrative = tension.narrative_explanation.strip() if tension.narrative_explanation else ""

        # Must have tension AND narrative
        if not tension.labels or len(narrative) < 30:
            return DimensionScore(
                name="内在一致性",
                score=0,
                rationale="缺少张力组合或心理叙事解释",
            )

        # Narrative should mention both sides of the contradiction
        label_keywords = [label[:2] for label in tension.labels]  # First 2 chars as proxy
        matched = sum(1 for kw in label_keywords if kw in narrative)

        if matched >= 2 and len(narrative) >= 50:
            return DimensionScore(
                name="内在一致性",
                score=2,
                rationale=f"张力标签({', '.join(tension.labels)})与叙事解释充分关联，narrative长度{len(narrative)}字",
            )

        if matched >= 1:
            return DimensionScore(
                name="内在一致性",
                score=1,
                rationale="部分标签在叙事中提及，但解释不够深入",
            )

        return DimensionScore(
            name="内在一致性",
            score=0,
            rationale="张力标签与叙事解释脱节",
        )

    # ------------------------------------------------------------------
    # Dimension 2: Situational Sensitivity
    # ------------------------------------------------------------------

    def _score_situational_sensitivity(self, persona: PersonaProfile) -> DimensionScore:
        """Same person should behave differently in different situations.

        Checks: Do language samples show variation? Does stress response
        differ from calm-state behaviour?
        """
        l4 = persona.layer4_scenarios
        samples = persona.language_samples

        # Must have situational variation markers
        stress = l4.stress_response.strip() if l4.stress_response else ""
        routine = l4.daily_routine.strip() if l4.daily_routine else ""

        if not stress or not routine:
            return DimensionScore(
                name="情境敏感性", score=0, rationale="缺少日常轨迹或压力反应描述"
            )

        # Check if stress response is meaningfully different from routine
        if stress == routine:
            return DimensionScore(
                name="情境敏感性", score=0, rationale="压力反应与日常轨迹完全相同"
            )

        # Language samples should show some emotional range
        if len(samples) >= 2:
            # Simple heuristic: samples should differ in sentiment markers
            positive_markers = ["好", "开心", "满意", "值得", "推荐"]
            negative_markers = ["后悔", "失望", "麻烦", "纠结", "担心"]

            pos_count = sum(1 for s in samples for m in positive_markers if m in s)
            neg_count = sum(1 for s in samples for m in negative_markers if m in s)

            if pos_count > 0 and neg_count > 0:
                return DimensionScore(
                    name="情境敏感性",
                    score=2,
                    rationale="语言样本展示正负情绪混合，压力反应与日常轨迹不同",
                )

            if pos_count > 0 or neg_count > 0:
                return DimensionScore(
                    name="情境敏感性",
                    score=1,
                    rationale="语言样本有情绪表达但方向单一",
                )

        return DimensionScore(
            name="情境敏感性",
            score=1,
            rationale="压力反应与日常轨迹不同，但语言样本情绪范围有限",
        )

    # ------------------------------------------------------------------
    # Dimension 3: Cognitive Limitation
    # ------------------------------------------------------------------

    def _score_cognitive_limitation(self, persona: PersonaProfile) -> DimensionScore:
        """Real consumers are not perfectly rational.

        Checks: Does the persona exhibit overly systematic behaviour?
        Do language samples contain evidence of bounded rationality?
        """
        l2 = persona.layer2_behavior
        samples_text = " ".join(persona.language_samples)

        # Penalise perfect rationality signals
        for pattern in self.PERFECT_RATIONALITY_PATTERNS:
            if re.search(pattern, samples_text):
                return DimensionScore(
                    name="认知有限性",
                    score=0,
                    rationale=f"语言样本中出现过度理性行为模式: {pattern}",
                )

        # Check for decision_style that claims perfect rationality
        decision = l2.decision_style.strip() if l2.decision_style else ""
        if "精确" in decision and "计算" in decision and "所有" in decision:
            return DimensionScore(
                name="认知有限性",
                score=0,
                rationale="决策风格声称对所有维度进行精确计算",
            )

        # Positive: some heuristic / gut-feel markers
        heuristic_markers = ["感觉", "大概", "差不多", "懒得", "随缘", "冲动", "直觉"]
        heuristic_count = sum(1 for m in heuristic_markers if m in samples_text)

        if heuristic_count >= 2:
            return DimensionScore(
                name="认知有限性",
                score=2,
                rationale=f"语言样本中出现{heuristic_count}处有限理性标记（直觉/大概/懒得等）",
            )

        if heuristic_count >= 1:
            return DimensionScore(
                name="认知有限性",
                score=1,
                rationale="语言样本中有少量有限理性表达",
            )

        # Neutral: no strong signals either way
        return DimensionScore(
            name="认知有限性",
            score=1,
            rationale="未检测到过度理性或明显有限理性信号",
        )

    # ------------------------------------------------------------------
    # Dimension 4: Social Friction
    # ------------------------------------------------------------------

    def _score_social_friction(self, persona: PersonaProfile) -> DimensionScore:
        """Real consumers show hesitation, contradiction, face-saving.

        Checks: Do language samples contain hedging, self-contradiction,
        or face-related expressions?
        """
        samples_text = " ".join(persona.language_samples)
        l3 = persona.layer3_psychology

        friction_markers = [
            "但是",
            "不过",
            "其实",
            "说实话",
            "纠结",
            "犹豫",
            "面子",
            "不好意思",
            "怕别人",
            "虽然",
            "可是",
        ]
        friction_count = sum(1 for m in friction_markers if m in samples_text)

        # Defense mechanism should be non-trivial
        defense = l3.defense_mechanism.strip() if l3.defense_mechanism else ""
        has_defense = len(defense) > 5 and "无" not in defense

        if friction_count >= 3 and has_defense:
            return DimensionScore(
                name="社会摩擦感",
                score=2,
                rationale=f"语言样本中出现{friction_count}处矛盾/犹豫标记，且有明确心理防御机制",
            )

        if friction_count >= 1 or has_defense:
            return DimensionScore(
                name="社会摩擦感",
                score=1,
                rationale="有少量摩擦标记或心理防御机制",
            )

        return DimensionScore(
            name="社会摩擦感",
            score=0,
            rationale="语言过于平顺，缺少犹豫、矛盾或面子考量",
        )

    # ------------------------------------------------------------------
    # Dimension 5: Temporal Continuity
    # ------------------------------------------------------------------

    def _score_temporal_continuity(self, persona: PersonaProfile) -> DimensionScore:
        """Behaviours should have historical continuity, not random.

        Checks: Does daily routine support stated lifestyle? Are there
        temporal markers in scenarios?
        """
        l1 = persona.layer1_demographics
        l4 = persona.layer4_scenarios

        routine = l4.daily_routine.strip() if l4.daily_routine else ""
        occupation = l1.occupation.strip() if l1.occupation else ""

        # Routine should reflect occupation
        occupation_routine_map: dict[str, list[str]] = {
            "学生": ["课", "宿舍", "图书馆", "考试", "作业"],
            "职": ["通勤", "上班", "加班", "公司", "工作"],
            "退休": ["公园", "买菜", "带孙", "晨练", "散步"],
            "自由": ["项目", "客户", "在家办公", "灵活"],
        }

        matched_occupation = False
        for occ_key, routine_markers in occupation_routine_map.items():
            if occ_key in occupation:
                matched = any(m in routine for m in routine_markers)
                if matched:
                    matched_occupation = True
                    break

        # Temporal markers (time-of-day references)
        time_markers = re.findall(r"[早中晚][0-9]{1,2}[点:]?|[0-9]{1,2}:[0-9]{2}", routine)

        if matched_occupation and len(time_markers) >= 1:
            return DimensionScore(
                name="时间延续性",
                score=2,
                rationale="日常轨迹与职业匹配，包含具体时间标记",
            )

        if matched_occupation or len(time_markers) >= 2:
            return DimensionScore(
                name="时间延续性",
                score=1,
                rationale="日常轨迹与职业部分匹配或包含时间标记",
            )

        return DimensionScore(
            name="时间延续性",
            score=0,
            rationale="日常轨迹与职业严重脱节，缺少时间标记",
        )

    # ------------------------------------------------------------------
    # Dimension 6: Language Naturalness
    # ------------------------------------------------------------------

    def _score_language_naturalness(self, persona: PersonaProfile) -> DimensionScore:
        """Real consumers speak colloquially, not in marketing speak.

        Checks: Are language samples free of jargon? Are they fragmented?
        Do they contain filler words?
        """
        samples = persona.language_samples
        samples_text = " ".join(samples)

        # Penalty: marketing jargon
        jargon_count = sum(1 for term in self.MARKETING_TERMS if term in samples_text)
        if jargon_count >= 2:
            return DimensionScore(
                name="语言自然度",
                score=0,
                rationale=f"语言样本中出现{jargon_count}处营销/学术术语",
            )

        if jargon_count == 1:
            return DimensionScore(
                name="语言自然度",
                score=1,
                rationale="出现1处术语，但整体尚可",
            )

        # Positive: colloquial markers
        colloquial_markers = ["吧", "呢", "啊", "嘛", "哎", "啦", "其实", "反正", "就是"]
        colloquial_count = sum(1 for m in colloquial_markers if m in samples_text)

        # Sentence length variation (real speech has short + long)
        lengths = [len(s) for s in samples]
        has_variation = max(lengths) - min(lengths) >= 10 if lengths else False

        if colloquial_count >= 3 and has_variation:
            return DimensionScore(
                name="语言自然度",
                score=2,
                rationale="口语化标记丰富，句子长度有变化",
            )

        if colloquial_count >= 1 or has_variation:
            return DimensionScore(
                name="语言自然度",
                score=1,
                rationale="有一定口语化特征或长度变化",
            )

        return DimensionScore(
            name="语言自然度",
            score=1,
            rationale="语言较规范但无严重术语问题",
        )

    # ------------------------------------------------------------------
    # Dimension 7: Knowledge Boundary
    # ------------------------------------------------------------------

    def _score_knowledge_boundary(self, persona: PersonaProfile) -> DimensionScore:
        """Real consumers admit ignorance; they don't BS about everything.

        Checks: Do language samples contain uncertainty markers?
        Does the persona claim expertise outside their domain?
        """
        samples_text = " ".join(persona.language_samples)

        # Positive: uncertainty / ignorance markers
        uncertainty_markers = [
            "不知道",
            "不清楚",
            "没研究",
            "没注意",
            "不太懂",
            "大概",
            "可能",
            "也许",
            "听说",
            "好像",
        ]
        uncertainty_count = sum(1 for m in uncertainty_markers if m in samples_text)

        # Negative: claiming universal expertise
        expertise_claims = ["我了解", "我精通", "我研究过", "所有品牌", "全部参数"]
        expertise_count = sum(1 for m in expertise_claims if m in samples_text)

        if expertise_count >= 2:
            return DimensionScore(
                name="知识边界感",
                score=0,
                rationale="语言样本中多次声称全面 expertise",
            )

        if uncertainty_count >= 2:
            return DimensionScore(
                name="知识边界感",
                score=2,
                rationale=f"语言样本中出现{uncertainty_count}处知识边界标记（不知道/不清楚等）",
            )

        if uncertainty_count >= 1 or expertise_count == 0:
            return DimensionScore(
                name="知识边界感",
                score=1,
                rationale="有一定谦逊表达或无明显 expertise 声称",
            )

        return DimensionScore(
            name="知识边界感",
            score=0,
            rationale="语言过于自信，缺少知识边界感",
        )
