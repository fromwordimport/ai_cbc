"""Natural-language scenario parser for CBC market simulation.

Converts free-text product descriptions (e.g. "华为 2999 元嵌入式 13 套") into
structured ``ProductScenario`` objects using the study's attribute definitions.
"""

from __future__ import annotations

import re
from typing import Any

from aicbc.analysis.models import ProductScenario
from aicbc.questionnaire.models import Attribute, AttributeType


def _normalize(text: str) -> str:
    """Normalize Chinese punctuation and whitespace."""
    return (
        text.replace("，", ",")
        .replace("。", ".")
        .replace(" ", "")
        .replace("　", "")
        .strip()
        .lower()
    )


def _extract_number_near(
    text: str,
    keyword: str | None = None,
    fallback: bool = True,
) -> float | None:
    """Extract the first number near an optional keyword.

    If ``keyword`` is provided, prefer numbers that follow the keyword within
    a short window.  When ``fallback`` is True (default), return the first
    number in the text if no keyword match is found.
    """
    if keyword:
        pattern = re.compile(
            re.escape(keyword) + r"[^\d]{0,10}(\d+(?:\.\d+)?)",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if match:
            return float(match.group(1))
        if not fallback:
            return None
    number_match = re.search(r"(\d+(?:\.\d+)?)", text)
    if number_match:
        return float(number_match.group(1))
    return None


def _is_number_part_of_level(text: str, match: re.Match[str], labels: set[str]) -> bool:
    """Return True if the number match is the start of a categorical level label."""
    if not labels:
        return False
    max_len = max(len(lbl) for lbl in labels)
    window = text[match.start() : match.start() + max_len + 2]
    return any(window.startswith(lbl) for lbl in labels)


def parse_nl_scenario(
    text: str,
    attributes: list[Attribute],
) -> ProductScenario:
    """Parse a natural-language product description into a ProductScenario.

    The parser uses the study's attribute definitions to map text fragments
    to attribute values:

    * Categorical / ordinal attributes: matches ``level.label`` or
      ``level.value`` (case-insensitive, longest match wins).
    * Price / continuous attributes: extracts the nearest numeric value,
      falling back to the first number in the text.

    Args:
        text: Free-text product description.
        attributes: Attribute definitions from the study design.

    Returns:
        A ``ProductScenario`` with as many attributes resolved as possible.
    """
    normalized = _normalize(text)
    parsed: dict[str, Any] = {}

    # Collect normalized categorical level labels for price disambiguation.
    categorical_labels: set[str] = set()
    for attr in attributes:
        if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
            for level in attr.levels:
                norm_label = _normalize(str(level.label))
                norm_value = _normalize(str(level.value))
                if norm_label:
                    categorical_labels.add(norm_label)
                if norm_value:
                    categorical_labels.add(norm_value)

    # Determine price attribute id if present
    price_attr = next(
        (attr for attr in attributes if attr.type == AttributeType.PRICE),
        None,
    )

    for attr in attributes:
        if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
            best_match: tuple[str, int] | None = None
            for level in attr.levels:
                candidates = {str(level.label), str(level.value)}
                for candidate in candidates:
                    norm_candidate = _normalize(candidate)
                    if not norm_candidate:
                        continue
                    idx = normalized.find(norm_candidate)
                    if idx != -1:
                        length = len(norm_candidate)
                        if best_match is None or length > best_match[1]:
                            best_match = (str(level.value), length)
            if best_match:
                parsed[attr.id] = best_match[0]

        elif attr.type == AttributeType.CONTINUOUS:
            value = _extract_number_near(normalized, _normalize(attr.name))
            if value is None:
                value = _extract_number_near(normalized)
            if value is not None:
                parsed[attr.id] = value

        elif attr.type == AttributeType.PRICE:
            # Prefer numbers followed by currency symbols / units
            for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:元|块|￥|¥)", normalized):
                value = float(match.group(1))
                if not _is_number_part_of_level(normalized, match, categorical_labels):
                    parsed[attr.id] = value
                    break
            if attr.id not in parsed:
                value = _extract_number_near(
                    normalized, _normalize(attr.name), fallback=False
                )
                if value is not None:
                    parsed[attr.id] = value
            if attr.id not in parsed:
                # Fall back to the first standalone number (not part of a
                # categorical level label).
                for match in re.finditer(r"(\d+(?:\.\d+)?)", normalized):
                    if not _is_number_part_of_level(normalized, match, categorical_labels):
                        parsed[attr.id] = float(match.group(1))
                        break

    # Fallback: if no explicit price attribute exists but we found a currency
    # number, store it under ``price`` so callers can inspect it.
    if price_attr is None and "price" not in parsed:
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:元|块|￥|¥)", normalized):
            if not _is_number_part_of_level(normalized, match, categorical_labels):
                parsed["price"] = float(match.group(1))
                break

    return ProductScenario(name=text.strip(), attributes=parsed)


def parse_nl_scenarios(
    texts: list[str],
    attributes: list[Attribute],
) -> list[ProductScenario]:
    """Parse multiple natural-language descriptions."""
    return [parse_nl_scenario(text, attributes) for text in texts]
