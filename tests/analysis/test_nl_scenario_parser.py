import pytest

from aicbc.analysis.nl_scenario_parser import parse_nl_scenario
from aicbc.questionnaire.models import Attribute, AttributeLevel, AttributeType


@pytest.fixture
def dishwasher_attributes():
    return [
        Attribute(
            id="brand",
            name="品牌",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="brand_0", label="美的"),
                AttributeLevel(value="brand_1", label="海尔"),
                AttributeLevel(value="brand_2", label="西门子"),
                AttributeLevel(value="brand_3", label="华为"),
            ],
        ),
        Attribute(
            id="price",
            name="价格",
            type=AttributeType.PRICE,
            levels=[
                AttributeLevel(value="0", label="0"),
                AttributeLevel(value="1", label="1"),
            ],
        ),
        Attribute(
            id="capacity",
            name="容量",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="capacity_0", label="8套"),
                AttributeLevel(value="capacity_1", label="13套"),
                AttributeLevel(value="capacity_2", label="15套"),
            ],
        ),
        Attribute(
            id="installation",
            name="安装方式",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="installation_0", label="台式"),
                AttributeLevel(value="installation_1", label="嵌入式"),
                AttributeLevel(value="installation_2", label="独立式"),
            ],
        ),
        Attribute(
            id="drying",
            name="烘干方式",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="drying_0", label="冷凝烘干"),
                AttributeLevel(value="drying_1", label="热风烘干"),
                AttributeLevel(value="drying_2", label="晶蕾烘干"),
            ],
        ),
    ]


def test_parse_full_description(dishwasher_attributes):
    text = "华为 2999 元嵌入式 13 套热风烘干"
    scenario = parse_nl_scenario(text, dishwasher_attributes)
    assert scenario.name == text
    assert scenario.attributes["brand"] == "brand_3"
    assert scenario.attributes["price"] == 2999
    assert scenario.attributes["capacity"] == "capacity_1"
    assert scenario.attributes["installation"] == "installation_1"
    assert scenario.attributes["drying"] == "drying_1"


def test_parse_partial_description(dishwasher_attributes):
    text = "美的 15套"
    scenario = parse_nl_scenario(text, dishwasher_attributes)
    assert scenario.attributes["brand"] == "brand_0"
    assert scenario.attributes["capacity"] == "capacity_2"
    assert "price" not in scenario.attributes
    assert "installation" not in scenario.attributes


def test_parse_price_without_currency(dishwasher_attributes):
    text = "西门子 3500 独立式"
    scenario = parse_nl_scenario(text, dishwasher_attributes)
    assert scenario.attributes["brand"] == "brand_2"
    assert scenario.attributes["installation"] == "installation_2"
    assert scenario.attributes["price"] == 3500


def test_longest_match_wins(dishwasher_attributes):
    # "冷凝烘干" contains "烘干"; longest match should win.
    text = "冷凝烘干"
    scenario = parse_nl_scenario(text, dishwasher_attributes)
    assert scenario.attributes["drying"] == "drying_0"


def test_empty_description_returns_name_only(dishwasher_attributes):
    scenario = parse_nl_scenario("   ", dishwasher_attributes)
    assert scenario.name == ""
    assert scenario.attributes == {}


def test_continuous_attribute():
    attrs = [
        Attribute(
            id="weight",
            name="重量",
            type=AttributeType.CONTINUOUS,
            levels=[
                AttributeLevel(value="0", label="0"),
                AttributeLevel(value="1", label="1"),
            ],
        ),
    ]
    scenario = parse_nl_scenario("重量 12.5 公斤", attrs)
    assert scenario.attributes["weight"] == 12.5


def test_no_attributes_returns_empty_scenario():
    scenario = parse_nl_scenario("任意文本", [])
    assert scenario.name == "任意文本"
    assert scenario.attributes == {}


def test_multiple_scenarios(dishwasher_attributes):
    from aicbc.analysis.nl_scenario_parser import parse_nl_scenarios

    texts = ["华为 2999 元嵌入式 13 套", "美的 15套"]
    scenarios = parse_nl_scenarios(texts, dishwasher_attributes)
    assert len(scenarios) == 2
    assert scenarios[0].attributes["brand"] == "brand_3"
    assert scenarios[1].attributes["brand"] == "brand_0"


def test_accuracy_threshold(dishwasher_attributes):
    """Check that the parser hits the 80% accuracy target on simple descriptions."""
    cases = [
        ("华为 2999 元嵌入式 13 套热风烘干", {"brand", "price", "capacity", "installation", "drying"}),
        ("美的 15套", {"brand", "capacity"}),
        ("西门子 3500 独立式", {"brand", "price", "installation"}),
        ("海尔 8套台式", {"brand", "capacity", "installation"}),
        ("冷凝烘干", {"drying"}),
    ]
    total_expected = sum(len(expected) for _, expected in cases)
    total_found = 0
    for text, expected in cases:
        scenario = parse_nl_scenario(text, dishwasher_attributes)
        for key in expected:
            if key in scenario.attributes:
                total_found += 1
    accuracy = total_found / total_expected
    assert accuracy >= 0.8, f"parser accuracy {accuracy:.2%} below 80% target"
