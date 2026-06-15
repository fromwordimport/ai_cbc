"""ECharts option builders for CBC analysis visualizations.

All functions return plain dicts that can be serialized to JSON and passed to
ECharts (e.g. via ``echarts-for-react`` on the frontend).
"""

from __future__ import annotations

from typing import Any

from aicbc.analysis.models import (
    ImportanceResponse,
    MarketSimResponse,
    WTPResponse,
)


def build_importance_chart_option(importance: ImportanceResponse) -> dict[str, Any]:
    """Return a bar-chart option for attribute importance."""
    if not importance or not importance.overall:
        return {}

    entries = sorted(
        importance.overall.items(),
        key=lambda x: x[1].mean,
        reverse=True,
    )
    names = [k for k, _ in entries]
    means = [round(v.mean * 100, 2) for _, v in entries]
    lowers = [round((v.ci_95_lower or v.mean) * 100, 2) for _, v in entries]
    uppers = [round((v.ci_95_upper or v.mean) * 100, 2) for _, v in entries]

    return {
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
            "formatter": "{b}<br/>重要性: {c}%",
        },
        "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": names,
            "axisLabel": {"rotate": 30, "interval": 0},
        },
        "yAxis": {"type": "value", "name": "重要性 (%)"},
        "series": [
            {
                "name": "重要性",
                "type": "bar",
                "data": [
                    {
                        "value": mean,
                        "ci": [lower, upper],
                    }
                    for mean, lower, upper in zip(means, lowers, uppers)
                ],
                "itemStyle": {
                    "color": "#5470c6",
                    "borderRadius": [4, 4, 0, 0],
                },
            }
        ],
    }


def build_importance_pie_option(importance: ImportanceResponse) -> dict[str, Any]:
    """Return a pie-chart option for attribute importance share."""
    if not importance or not importance.overall:
        return {}

    data = [
        {"name": name, "value": round(stats.mean * 100, 2)}
        for name, stats in sorted(
            importance.overall.items(), key=lambda x: x[1].mean, reverse=True
        )
    ]
    return {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c}% ({d}%)"},
        "legend": {"orient": "vertical", "right": 10, "top": "center"},
        "series": [
            {
                "name": "属性重要性",
                "type": "pie",
                "radius": ["40%", "70%"],
                "avoidLabelOverlap": False,
                "itemStyle": {
                    "borderRadius": 8,
                    "borderColor": "#fff",
                    "borderWidth": 2,
                },
                "label": {"show": True, "formatter": "{b}\n{c}%"},
                "data": data,
            }
        ],
    }


def build_utility_distribution_option(
    individual_utilities: dict[str, dict[str, float]],
    top_n: int = 8,
) -> dict[str, Any]:
    """Return a boxplot-ready option for individual utility distributions.

    The frontend can render this as a boxplot or use the computed quartiles.
    """
    if not individual_utilities:
        return {}

    import numpy as np

    param_values: dict[str, list[float]] = {}
    for utils in individual_utilities.values():
        for param, value in utils.items():
            param_values.setdefault(param, []).append(value)

    stats: list[dict[str, Any]] = []
    for param, values in param_values.items():
        arr = np.array(values)
        stats.append(
            {
                "param": param,
                "min": float(np.min(arr)),
                "q1": float(np.percentile(arr, 25)),
                "median": float(np.median(arr)),
                "q3": float(np.percentile(arr, 75)),
                "max": float(np.max(arr)),
                "mean": float(np.mean(arr)),
            }
        )

    # Keep only the most variable parameters if there are too many
    stats.sort(key=lambda x: x["q3"] - x["q1"], reverse=True)
    stats = stats[:top_n]

    return {
        "tooltip": {"trigger": "item"},
        "xAxis": {
            "type": "category",
            "data": [s["param"] for s in stats],
            "axisLabel": {"rotate": 30, "interval": 0},
        },
        "yAxis": {"type": "value", "name": "效用"},
        "series": [
            {
                "name": "效用分布",
                "type": "boxplot",
                "data": [
                    [s["min"], s["q1"], s["median"], s["q3"], s["max"]]
                    for s in stats
                ],
            }
        ],
    }


def build_market_share_option(market_sim: MarketSimResponse) -> dict[str, Any]:
    """Return a bar/pie option for market simulation shares."""
    if not market_sim or not market_sim.scenarios:
        return {}

    names = [s.name for s in market_sim.scenarios]
    values = [round(s.predicted_share * 100, 2) for s in market_sim.scenarios]

    return {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {
            "type": "category",
            "data": names,
            "axisLabel": {"interval": 0, "rotate": 30 if len(names) > 5 else 0},
        },
        "yAxis": {"type": "value", "name": "市场份额 (%)", "max": 100},
        "series": [
            {
                "name": "市场份额",
                "type": "bar",
                "data": values,
                "itemStyle": {"borderRadius": [4, 4, 0, 0]},
                "barMaxWidth": 80,
            }
        ],
    }


def build_wtp_chart_option(wtp: WTPResponse) -> dict[str, Any]:
    """Return a grouped bar option for WTP comparisons."""
    if not wtp or not wtp.wtp_values:
        return {}

    categories: list[str] = []
    values: list[float] = []
    for attr_name, attr_data in wtp.wtp_values.items():
        for comp in attr_data.comparisons:
            label = f"{attr_name}: {comp.from_level} → {comp.to_level}"
            categories.append(label)
            values.append(round(comp.wtp_mean, 2))

    return {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {
            "type": "category",
            "data": categories,
            "axisLabel": {"interval": 0, "rotate": 30},
        },
        "yAxis": {"type": "value", "name": "WTP (¥)"},
        "series": [
            {
                "name": "WTP 均值",
                "type": "bar",
                "data": values,
                "itemStyle": {"color": "#91cc75", "borderRadius": [4, 4, 0, 0]},
            }
        ],
    }


def build_dashboard_option(
    importance: ImportanceResponse | None = None,
    market_sim: MarketSimResponse | None = None,
) -> dict[str, Any]:
    """Combine the most commonly used charts into a dashboard payload."""
    return {
        "importance_bar": build_importance_chart_option(importance) if importance else {},
        "importance_pie": build_importance_pie_option(importance) if importance else {},
        "market_share": build_market_share_option(market_sim) if market_sim else {},
    }
