"""Batch bias audit test — simulates a full study cohort audit.

This test generates a diverse batch of 24 personas (simulating a real study sample)
and runs the BiasAuditor across all of them to produce an aggregate audit report.
"""

from __future__ import annotations

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
from aicbc.core.scoring.bias_auditor import BiasAuditor

# ---------------------------------------------------------------------------
# Helper: persona builder
# ---------------------------------------------------------------------------


def _make_persona(
    persona_id: str = "persona-test-001",
    gender: str = "女",
    city: str = "新一线城市",
    occupation: str = "互联网产品经理",
    income: str = "15-30万元",
    price_sensitivity: str = "中等敏感",
    decision_style: str = "理性比较型",
    samples: list[str] | None = None,
    age: str = "28岁",
    education: str = "本科",
    brand_loyalty: str = "中等",
) -> PersonaProfile:
    """Build a persona with configurable bias-relevant fields."""
    return PersonaProfile(
        persona_id=persona_id,
        segment="测试群体",
        layer1_demographics=Layer1Demographics(
            age=age,
            gender=gender,
            city=city,
            income=income,
            occupation=occupation,
            education=education,
            marital_status="已婚无孩",
            living_type="自有住房",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity=price_sensitivity,
            purchase_channels=["京东", "天猫"],
            decision_style=decision_style,
            brand_loyalty=brand_loyalty,
            information_source=["小红书", "知乎"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率", "品质"],
            core_anxieties=["时间不够"],
            tension_combination=TensionCombination(
                labels=["A", "B"],
                narrative_explanation=(
                    "她追求精致生活却总在凑单后退掉不需要的商品，这种矛盾源于她既想享受品质又害怕浪费金钱的深层焦虑，"
                    "这是她内心最真实的状态。"
                ),
            ),
            secret_motivation="用科技产品证明品味",
            defense_mechanism="合理化",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="早7点起床，通勤40分钟",
            purchase_trigger="被小红书种草",
            stress_response="焦虑时刷购物APP",
            social_behavior="朋友圈少发",
        ),
        language_samples=samples
        or [
            "洗碗机用起来真的很方便，洗完的碗都亮晶晶的。",
            "对比了好几个品牌，最后还是选了这个性价比高的。",
            "安装师傅非常专业，只用了半小时就全部搞定了。",
        ],
        dishwasher_context=DishwasherContext(
            purchase_constraints=["厨房小"],
            decision_factors=["价格"],
            ignored_factors=["外观"],
        ),
        generation_metadata=GenerationMetadata(),
    )


# ---------------------------------------------------------------------------
# Batch audit test
# ---------------------------------------------------------------------------


class TestBatchBiasAudit:
    """Full batch bias audit simulating a study cohort of 24 personas."""

    def test_full_batch_audit_report(self) -> None:
        """Audit 24 diverse personas and verify aggregate statistics."""
        auditor = BiasAuditor()

        personas = [
            # 1. Clean baseline
            _make_persona(persona_id="persona-audit-001"),
            # 2. Gender stereotype — female + emotional
            _make_persona(
                persona_id="persona-audit-002",
                gender="女",
                price_sensitivity="颜值至上，只看外观，不关注参数，容易被种草，情绪化决策",
                decision_style="感性冲动，只看颜值，完全不理性",
            ),
            # 3. Gender stereotype — male + tech-focused
            _make_persona(
                persona_id="persona-audit-003",
                gender="男",
                price_sensitivity="参数党，只看性能，不关心价格，技术专家",
                decision_style="理性分析，只看参数",
            ),
            # 4. Region-income stereotype (low-tier city + low income)
            _make_persona(
                persona_id="persona-audit-004",
                city="县城",
                income="3万元以下",
                occupation="工厂工人",
            ),
            # 5. Region-income stereotype (town + low income)
            _make_persona(
                persona_id="persona-audit-005",
                city="乡镇",
                income="3万元以下",
                occupation="农民",
            ),
            # 6. Occupation-income anomaly — HIGH SEVERITY
            _make_persona(
                persona_id="persona-audit-006",
                occupation="大学生",
                income="100万元以上",
                age="20岁",
            ),
            # 7. Occupation-income anomaly — HIGH SEVERITY
            _make_persona(
                persona_id="persona-audit-007",
                occupation="退休职工",
                income="50-100万元",
                age="65岁",
            ),
            # 8. Biased language samples — HIGH SEVERITY
            _make_persona(
                persona_id="persona-audit-008",
                samples=[
                    "女人天生就是喜欢买东西的，这是典型的女性消费行为。",
                    "我们男的买东西就是理性，不像女的那么冲动。",
                    "穷人思维就是只关注价格，根本看不到长远价值。",
                ],
            ),
            # 9. Average template — diversity flag
            _make_persona(
                persona_id="persona-audit-009",
                age="28岁",
                education="本科",
                occupation="互联网运营",
                city="新一线城市",
                income="15-30万元",
            ),
            # 10. Clean — male professional
            _make_persona(
                persona_id="persona-audit-010",
                gender="男",
                city="一线城市",
                occupation="金融分析师",
                income="30-50万元",
                price_sensitivity="对品质敏感，不为价格妥协",
                decision_style="数据驱动，理性分析",
            ),
            # 11. Clean — female teacher
            _make_persona(
                persona_id="persona-audit-011",
                gender="女",
                city="二线城市",
                occupation="教师",
                income="8-15万元",
                price_sensitivity="比较理性，注重性价比",
                decision_style="口碑参考型",
            ),
            # 12. Male — light stereotype
            _make_persona(
                persona_id="persona-audit-012",
                gender="男",
                price_sensitivity="只看性能参数",
                decision_style="参数党",
            ),
            # 13. Third-tier city
            _make_persona(
                persona_id="persona-audit-013",
                city="三四线城市",
                income="8-15万元",
                occupation="小企业主",
            ),
            # 14. Student — normal income (clean)
            _make_persona(
                persona_id="persona-audit-014",
                occupation="大学生",
                income="3万元以下",
                age="21岁",
            ),
            # 15. Retiree — normal income (clean)
            _make_persona(
                persona_id="persona-audit-015",
                occupation="退休职工",
                income="8-15万元",
                age="68岁",
            ),
            # 16. Language with mild bias term
            _make_persona(
                persona_id="persona-audit-016",
                samples=[
                    "男人就应该负责家里的大件采购，这是传统。",
                    "对比了好几个品牌，最后还是选了这个性价比高的。",
                    "安装师傅非常专业，只用了半小时就全部搞定了。",
                ],
            ),
            # 17. Highly average — diversity flag
            _make_persona(
                persona_id="persona-audit-017",
                age="25-34岁",
                education="本科",
                occupation="互联网白领",
                city="一线城市",
                income="15-30万元",
            ),
            # 18. Clean — female lawyer
            _make_persona(
                persona_id="persona-audit-018",
                gender="女",
                city="一线城市",
                occupation="律师",
                income="30-50万元",
                price_sensitivity="愿意为品质支付溢价",
                decision_style="专业评估型",
            ),
            # 19. Clean — male chef
            _make_persona(
                persona_id="persona-audit-019",
                gender="男",
                city="二线城市",
                occupation="厨师",
                income="8-15万元",
                price_sensitivity="实用主义，关注耐用性",
                decision_style="经验判断型",
            ),
            # 20. Region stereotype
            _make_persona(
                persona_id="persona-audit-020",
                city="县城",
                income="3万元以下",
                occupation="超市收银员",
            ),
            # 21. Freelancer — borderline income
            _make_persona(
                persona_id="persona-audit-021",
                occupation="自由职业者",
                income="30-50万元",
                age="35岁",
            ),
            # 22. Clean — young designer
            _make_persona(
                persona_id="persona-audit-022",
                age="24岁",
                gender="女",
                city="新一线城市",
                occupation="UI设计师",
                income="15-30万元",
                price_sensitivity="设计感优先，价格其次",
                decision_style="视觉驱动型",
            ),
            # 23. Male — emotional (non-stereotypical, should pass)
            _make_persona(
                persona_id="persona-audit-023",
                gender="男",
                price_sensitivity="注重情感价值，愿意为心动买单",
                decision_style="直觉驱动型",
            ),
            # 24. Another average template
            _make_persona(
                persona_id="persona-audit-024",
                age="28岁",
                education="本科",
                occupation="互联网产品经理",
                city="新一线城市",
                income="15-30万元",
            ),
        ]

        # Run batch audit
        result = auditor.audit_batch(personas)

        # --- Assertions on aggregate statistics ---
        assert result["total_audited"] == 24
        assert result["passed"] + result["failed"] == 24
        assert 0 <= result["pass_rate"] <= 1
        assert result["total_findings"] >= 0
        assert result["high_severity_findings"] >= 3  # At least: 2 occupation-income + 1 language

        # --- Category breakdown checks ---
        categories = result["findings_by_category"]
        assert (
            "gender" in categories or result["total_findings"] == 0
        )  # May or may not have gender flags
        assert "occupation-income" in categories  # Must have occupation-income findings
        assert "language" in categories  # Must have language findings
        assert "region" in categories  # Must have region findings

        # --- Individual high-severity checks ---
        for p in personas:
            r = auditor.audit(p)
            if p.persona_id in ("persona-audit-006", "persona-audit-007"):
                # These should fail due to high-severity occupation-income anomaly
                occ_findings = [f for f in r.findings if f.rule_id == "BIAS-OCC-001"]
                assert len(occ_findings) == 1
                assert occ_findings[0].severity == "high"

            if p.persona_id == "persona-audit-008":
                # Should have multiple language bias findings
                lang_findings = [f for f in r.findings if f.category == "language"]
                assert len(lang_findings) >= 2
                assert all(f.severity == "high" for f in lang_findings)

        # --- Print audit report (visible in pytest -s) ---
        print("\n" + "=" * 60)
        print("偏见审计报告 (Bias Audit Report)")
        print("=" * 60)
        print(f"审计样本总数: {result['total_audited']}")
        print(f"通过数: {result['passed']}")
        print(f"失败数: {result['failed']}")
        print(f"通过率: {result['pass_rate']:.1%}")
        print(f"发现偏见项总数: {result['total_findings']}")
        print(f"高危偏见项数: {result['high_severity_findings']}")
        print("-" * 60)
        print("按类别分布:")
        for cat, cnt in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {cnt} 项")
        print("=" * 60)

        # Detailed findings
        print("\n详细发现 (按画像):")
        print("=" * 60)
        for p in personas:
            r = auditor.audit(p)
            if r.findings:
                demo = p.layer1_demographics
                print(
                    f"\n[{p.persona_id}] {demo.gender} | {demo.city} | "
                    f"{demo.occupation} | {demo.income}"
                )
                for f in r.findings:
                    flag = (
                        "!!!" if f.severity == "high" else ("!!" if f.severity == "medium" else "!")
                    )
                    print(f"  {flag} [{f.rule_id}] ({f.severity}) {f.description}")

        print("\n" + "=" * 60)
        print("审计结论")
        print("=" * 60)
        if result["failed"] > 0:
            print(f"结果: FAILED — {result['failed']} 个样本未通过偏见审计")
            print("建议: 需要重新生成或人工审核失败的样本，特别关注高危项")
        else:
            print("结果: PASSED — 所有样本通过偏见审计")
        if result["high_severity_findings"] > 0:
            print(f"警告: 存在 {result['high_severity_findings']} 项高危偏见发现，需立即处理")
        print("=" * 60)
