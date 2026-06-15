"""Report builder for CBC analysis results.

Supports Markdown and HTML outputs.  PDF output is available when ``fpdf2``
is installed; otherwise callers should handle the missing dependency gracefully.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aicbc.analysis.models import (
    AnalysisResultResponse,
    ImportanceResponse,
    MarketSimResponse,
    WTPResponse,
)


class ReportBuilder:
    """Build human-readable CBC analysis reports."""

    def __init__(
        self,
        analysis_result: AnalysisResultResponse,
        importance: ImportanceResponse | None = None,
        wtp: WTPResponse | None = None,
        market_sim: MarketSimResponse | None = None,
    ) -> None:
        self.analysis = analysis_result
        self.importance = importance
        self.wtp = wtp
        self.market_sim = market_sim

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def to_markdown(self) -> str:
        """Return a Markdown report string."""
        lines: list[str] = []
        lines.append(f"# CBC 分析报告：{self.analysis.study_id}")
        lines.append("")
        lines.append(f"- **分析 ID**: `{self.analysis.analysis_id}`")
        lines.append(f"- **模型类型**: {self.analysis.model_type.upper()}")
        lines.append(f"- **状态**: {self.analysis.status}")
        lines.append(f"- **生成时间**: {self._format_time(self.analysis.completed_at)}")
        lines.append(f"- **处理耗时**: {self.analysis.processing_time_seconds:.2f}s")
        lines.append("")

        lines.append("## 收敛诊断")
        conv = self.analysis.convergence
        lines.append(f"- **R-hat Max**: {conv.rhat_max:.3f} {'✅' if conv.converged else '⚠️'}")
        lines.append(f"- **ESS Bulk Min**: {conv.ess_bulk_min:.0f}")
        lines.append(f"- **ESS Tail Min**: {conv.ess_tail_min:.0f}")
        lines.append(f"- **发散次数**: {conv.divergences}")
        lines.append(f"- **是否收敛**: {'是' if conv.converged else '否'}")
        lines.append("")

        lines.append("## 属性重要性")
        if self.importance and self.importance.overall:
            lines.append("| 排名 | 属性 | 重要性均值 | 标准差 | 95% CI 下限 | 95% CI 上限 |")
            lines.append("|------|------|------------|--------|-------------|-------------|")
            sorted_items = sorted(
                self.importance.overall.items(),
                key=lambda x: x[1].mean,
                reverse=True,
            )
            for rank, (attr, stats) in enumerate(sorted_items, start=1):
                lines.append(
                    f"| {rank} | {attr} | {stats.mean:.4f} | {stats.std:.4f} | "
                    f"{stats.ci_95_lower:.4f} | {stats.ci_95_upper:.4f} |"
                )
        else:
            lines.append("_重要性结果不可用_")
        lines.append("")

        if self.wtp:
            lines.append("## 支付意愿 (WTP)")
            pc = self.wtp.price_coefficient_summary
            lines.append(
                f"- **价格系数均值**: {pc.mean:.4f} "
                f"({'✅ 为负' if pc.mean < 0 else '⚠️ 非负'})"
            )
            lines.append(f"- **负系数比例**: {pc.negative_rate * 100:.1f}%")
            lines.append(f"- **正异常值数**: {pc.n_positive_outliers}")
            lines.append("")
            lines.append("| 属性 | 从等级 | 到等级 | WTP 均值 | WTP 中位数 | 95% CI |")
            lines.append("|------|--------|--------|----------|------------|--------|")
            for attr_name, attr_data in self.wtp.wtp_values.items():
                for comp in attr_data.comparisons:
                    ci = f"[{comp.ci_95_lower:.2f}, {comp.ci_95_upper:.2f}]"
                    lines.append(
                        f"| {attr_name} | {comp.from_level} | {comp.to_level} | "
                        f"{comp.wtp_mean:.2f} | {comp.wtp_median:.2f} | {ci} |"
                    )
            lines.append("")

        if self.market_sim:
            lines.append("## 市场份额模拟")
            lines.append("| 场景 | 预测份额 | 95% CI |")
            lines.append("|------|----------|--------|")
            for share in self.market_sim.scenarios:
                ci = f"[{share.share_ci_95_lower * 100:.1f}%, {share.share_ci_95_upper * 100:.1f}%]"
                lines.append(
                    f"| {share.name} | {share.predicted_share * 100:.2f}% | {ci} |"
                )
            lines.append("")

        lines.append("---")
        lines.append("*本报告由 AI_CBC 自动生成，仅供研究参考。*")
        return "\n".join(lines)

    def to_html(self) -> str:
        """Return an HTML report string (basic styling included)."""
        md = self.to_markdown()
        # Convert Markdown tables to HTML
        html_body = self._markdown_to_html(md)
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>CBC 分析报告 - {self.analysis.study_id}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; max-width: 960px; margin: 40px auto; padding: 0 20px; color: #333; }}
    h1 {{ color: #1a1a1a; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
    h2 {{ color: #2c3e50; margin-top: 32px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
    th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
    th {{ background: #f5f5f5; font-weight: 600; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 4px; }}
    ul {{ padding-left: 20px; }}
  </style>
</head>
<body>
{html_body}
</body>
</html>"""

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _format_time(value: datetime | None) -> str:
        if value is None:
            return "N/A"
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.strftime("%Y-%m-%d %H:%M:%S UTC")

    @staticmethod
    def _markdown_to_html(md: str) -> str:
        """Convert a small subset of Markdown to HTML.

        Handles headers, lists, paragraphs, and pipe tables.
        """
        lines = md.split("\n")
        out: list[str] = []
        in_table = False
        table_rows: list[str] = []

        def flush_table() -> None:
            nonlocal in_table
            if not table_rows:
                return
            out.append("<table>")
            header = table_rows[0]
            cells = [c.strip() for c in header.split("|") if c.strip()]
            out.append("  <thead><tr>" + "".join(f"<th>{ReportBuilder._escape_html(c)}</th>" for c in cells) + "</tr></thead>")
            out.append("  <tbody>")
            for row in table_rows[2:]:  # skip header and separator
                cells = [c.strip() for c in row.split("|") if c.strip()]
                if not cells:
                    continue
                out.append("    <tr>" + "".join(f"<td>{ReportBuilder._escape_html(c)}</td>" for c in cells) + "</tr>")
            out.append("  </tbody></table>")
            table_rows.clear()
            in_table = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                in_table = True
                table_rows.append(stripped)
                continue
            if in_table:
                flush_table()

            if stripped.startswith("# "):
                out.append(f"<h1>{ReportBuilder._escape_html(stripped[2:])}</h1>")
            elif stripped.startswith("## "):
                out.append(f"<h2>{ReportBuilder._escape_html(stripped[3:])}</h2>")
            elif stripped.startswith("- "):
                out.append(f"<li>{ReportBuilder._escape_html(stripped[2:])}</li>")
            elif stripped == "":
                out.append("<br>")
            else:
                out.append(f"<p>{ReportBuilder._escape_html(stripped)}</p>")

        flush_table()
        return "\n".join(out)

    @staticmethod
    def _escape_html(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )


def build_report(
    analysis_result: AnalysisResultResponse,
    importance: ImportanceResponse | None = None,
    wtp: WTPResponse | None = None,
    market_sim: MarketSimResponse | None = None,
    format: str = "markdown",
) -> str:
    """Convenience wrapper to build a report in the requested format.

    Args:
        analysis_result: Complete analysis result.
        importance: Optional attribute importance response.
        wtp: Optional WTP response.
        market_sim: Optional market simulation response.
        format: ``markdown`` or ``html``.

    Returns:
        Markdown or HTML string.
    """
    builder = ReportBuilder(analysis_result, importance, wtp, market_sim)
    fmt = format.lower()
    if fmt == "markdown":
        return builder.to_markdown()
    if fmt == "html":
        return builder.to_html()
    raise ValueError(f"Unsupported report format: {format}")
