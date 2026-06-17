"""Quick smoke test for BiasAuditor v2 with 24-pattern library."""

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


def make(gender, city, occupation, income, price_sens, decision, samples=None):
    return PersonaProfile(
        persona_id="persona-test-001",
        segment="test",
        layer1_demographics=Layer1Demographics(
            age="28岁",
            gender=gender,
            city=city,
            income=income,
            occupation=occupation,
            education="本科",
            marital_status="已婚",
            living_type="自有住房",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity=price_sens,
            purchase_channels=[],
            decision_style=decision,
            brand_loyalty="中等",
            information_source=[],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=[],
            core_anxieties=[],
            tension_combination=TensionCombination(
                labels=["A", "B"],
                narrative_explanation="她追求精致生活却总在凑单后退掉不需要的商品，这种矛盾源于她既想享受品质又害怕浪费金钱的深层焦虑，正是这种内在冲突塑造了她独特的消费决策模式，也是她内心最真实的状态写照。",
            ),
            secret_motivation="品味证明",
            defense_mechanism="合理化",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="早7点起床",
            purchase_trigger="被小红书种草",
            stress_response="焦虑时刷购物APP",
            social_behavior="朋友圈少发",
        ),
        language_samples=samples
        or [
            "洗碗机用起来真的很方便，洗完后碗都亮晶晶的，感觉生活质量提升了不少。",
            "对比了好几个品牌和型号，最后还是选了这个性价比最高的款式。",
            "安装师傅非常专业而且快速，只用了不到一个小时就全部搞定了。",
        ],
        dishwasher_context=DishwasherContext(
            purchase_constraints=[],
            decision_factors=[],
            ignored_factors=[],
        ),
        generation_metadata=GenerationMetadata(),
    )


def test_student_high_income_fails():
    """Student + 100w income should fail bias audit (SP-016)."""
    auditor = BiasAuditor()
    p = make("女", "新一线", "大学生", "100万元以上", "中等敏感", "理性比较型")
    r = auditor.audit(p)
    # Should have at least one occupation-income finding
    occ = [f for f in r.findings if f.category == "occupation-income"]
    assert len(occ) >= 1, (
        f"Expected occupation-income finding, got {[f.rule_id for f in r.findings]}"
    )
    assert r.status == "FAILED", f"Expected FAILED, got {r.status}"
    assert r.high_severity_count >= 1, f"Expected high severity, got {r.high_severity_count}"
    print(
        f"  [OK] Student+100w: status={r.status}, findings={len(r.findings)}, high={r.high_severity_count}"
    )


def test_female_emotional_stereotype():
    """Female + emotional keywords should trigger gender stereotype patterns."""
    auditor = BiasAuditor()
    p = make(
        "女",
        "新一线",
        "白领",
        "15-30万元",
        "感性消费，冲动消费，情绪化决策，容易被种草",
        "感性冲动，只看颜值",
    )
    r = auditor.audit(p)
    gender = [f for f in r.findings if f.category == "gender"]
    assert len(gender) >= 1, (
        f"Expected gender findings, got none. Findings: {[f.rule_id for f in r.findings]}"
    )
    print(f"  [OK] Female+stereotype: status={r.status}, gender_findings={len(gender)}")


def test_language_bias():
    """Explicit bias terms in language samples should be caught."""
    auditor = BiasAuditor()
    p = make(
        "女",
        "新一线",
        "白领",
        "15-30万元",
        "中等敏感",
        "理性比较型",
        samples=[
            "女人天生就是喜欢买东西的，这就是典型的女性消费行为模式。",
            "我们男的买东西就是理性决策，不像女的那么感性冲动消费。",
            "穷人思维就是只关注价格，根本看不到长远的品质价值。",
        ],
    )
    r = auditor.audit(p)
    lang = [f for f in r.findings if f.category == "language"]
    assert len(lang) >= 2, f"Expected >=2 language findings, got {len(lang)}"
    assert all(f.severity == "high" for f in lang)
    print(f"  [OK] Language bias: status={r.status}, lang_findings={len(lang)}")


def test_clean_persona_passes():
    """A well-designed persona without stereotypes should PASS."""
    auditor = BiasAuditor()
    p = make("女", "二线城市", "教师", "8-15万元", "比较理性，注重性价比", "口碑参考型")
    r = auditor.audit(p)
    # May have diversity flag (low severity), but should not FAIL
    assert r.status == "PASSED", (
        f"Expected PASSED, got {r.status}: {[f.rule_id for f in r.findings]}"
    )
    print(f"  [OK] Clean persona: status={r.status}, findings={len(r.findings)}")


def test_24_patterns_categories():
    """Verify all 6 categories are represented in the 24 patterns."""
    from aicbc.core.scoring.stereotype_patterns import STEREOTYPE_PATTERNS

    cats = {p["category"] for p in STEREOTYPE_PATTERNS}
    expected = {"gender", "age", "region", "occupation-income", "occupation", "ethnicity", "income"}
    missing = expected - cats
    assert not missing, f"Missing categories: {missing}"
    # Check counts
    for cat in expected:
        count = sum(1 for p in STEREOTYPE_PATTERNS if p["category"] == cat)
        print(f"  [OK] Category '{cat}': {count} patterns")


if __name__ == "__main__":
    print("=== BiasAuditor v2 Quick Check ===\n")
    test_24_patterns_categories()
    print()
    test_student_high_income_fails()
    test_female_emotional_stereotype()
    test_language_bias()
    test_clean_persona_passes()
    print("\n=== All checks passed! ===")
