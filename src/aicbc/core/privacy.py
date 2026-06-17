"""Privacy utilities for PII detection and redaction.

Provides regex-based detection and irreversible redaction of common
personally identifiable information (PII) in text and structured data.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PIIMatch:
    """A detected PII segment."""

    pii_type: str
    start: int
    end: int
    value: str


# Regex patterns for common PII types in Chinese contexts.
_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "mobile_phone": re.compile(r"(?<![\d])1[3-9]\d{9}(?![\d])"),
    "id_card": re.compile(r"(?<![\d])\d{17}[\dXx]|\d{15}(?![\d])"),
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "bank_card": re.compile(r"(?<![\d])\d{16,19}(?![\d])"),
}

# Common Chinese surnames for naive name detection.
_COMMON_SURNAMES = set(
    "王李张刘陈杨黄赵周吴徐孙马朱胡郭何林罗高郑梁谢宋唐许韩冯邓曹彭曾肖田董潘袁蔡蒋余于杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏付方白邹孟熊秦邱江尹薛闫段雷侯龙史黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
)


def _hash_value(value: str) -> str:
    """Return a short irreversible hash of a value."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def detect_pii(text: str) -> list[PIIMatch]:
    """Detect PII segments in *text*.

    Returns a list of ``PIIMatch`` objects sorted by position.  Overlapping
    matches are resolved by preferring the longer match.
    """
    candidates: list[PIIMatch] = []
    for pii_type, pattern in _PII_PATTERNS.items():
        for match in pattern.finditer(text):
            candidates.append(
                PIIMatch(
                    pii_type=pii_type,
                    start=match.start(),
                    end=match.end(),
                    value=match.group(),
                )
            )
    candidates.extend(_detect_names(text))

    # Resolve overlaps: keep longer matches; on tie, keep the earlier one.
    candidates.sort(key=lambda m: (m.start, -(m.end - m.start)))
    filtered: list[PIIMatch] = []
    for match in candidates:
        if not any(other.start <= match.start and other.end >= match.end for other in filtered):
            filtered.append(match)
    return sorted(filtered, key=lambda m: m.start)


def _detect_names(text: str) -> list[PIIMatch]:
    """Naively detect 2-4 character Chinese names.

    Looks for sequences starting with a common surname followed by 1-3
    Chinese characters.  This is intentionally conservative to avoid
    over-matching regular words.
    """
    matches: list[PIIMatch] = []
    i = 0
    chars = list(text)
    while i < len(chars) - 1:
        if chars[i] in _COMMON_SURNAMES:
            # Try to consume 1-3 additional CJK characters.
            j = i + 1
            while j < len(chars) and j <= i + 3 and "一" <= chars[j] <= "鿿":
                j += 1
            if j > i + 1:
                value = "".join(chars[i:j])
                matches.append(PIIMatch("name", i, j, value))
                i = j
                continue
        i += 1
    return matches


def redact_pii(
    text: str,
    *,
    irreversible: bool = True,
    mask_char: str = "*",
) -> str:
    """Redact all detected PII from *text*.

    Args:
        text: Input string that may contain PII.
        irreversible: If True, replace the PII value with a fixed-length
            irreversible hash so the original cannot be recovered.  If False,
            apply a conventional mask (e.g. 138****1234).
        mask_char: Character used when building conventional masks.

    Returns:
        Redacted string with the same length and structure where possible.
    """
    matches = detect_pii(text)
    if not matches:
        return text

    parts: list[str] = []
    cursor = 0
    for match in matches:
        parts.append(text[cursor : match.start])
        parts.append(_redact_match(match, irreversible=irreversible, mask_char=mask_char))
        cursor = match.end
    parts.append(text[cursor:])
    return "".join(parts)


def _redact_match(
    match: PIIMatch,
    *,
    irreversible: bool,
    mask_char: str,
) -> str:
    """Redact a single PII match."""
    value = match.value
    length = len(value)

    if irreversible:
        # Use a hash prefix so the redacted value is clearly artificial and
        # carries no recoverable information about the original.
        return f"[REDACTED:{match.pii_type}:{_hash_value(value)}]"

    if match.pii_type == "mobile_phone" and length == 11:
        return f"{value[:3]}{mask_char * 4}{value[7:]}"
    if match.pii_type == "id_card" and length >= 15:
        return f"{value[:3]}{mask_char * (length - 7)}{value[-4:]}"
    if match.pii_type == "email":
        local, _, domain = value.partition("@")
        if len(local) > 1:
            return f"{local[0]}{mask_char * (len(local) - 1)}@{domain}"
        return f"{mask_char}@{domain}"
    if match.pii_type == "bank_card" and length >= 8:
        return f"{mask_char * (length - 4)}{value[-4:]}"
    if match.pii_type == "name":
        return f"{value[0]}{mask_char * (length - 1)}"

    # Fallback: mask everything.
    return mask_char * length


def redact_dict(
    data: dict[str, Any],
    *,
    irreversible: bool = True,
) -> dict[str, Any]:
    """Recursively redact PII from string values in a dictionary.

    Only string values are processed; other types are passed through.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = redact_pii(value, irreversible=irreversible)
        elif isinstance(value, dict):
            result[key] = redact_dict(value, irreversible=irreversible)
        elif isinstance(value, list):
            result[key] = [
                redact_pii(v, irreversible=irreversible)
                if isinstance(v, str)
                else redact_dict(v, irreversible=irreversible)
                if isinstance(v, dict)
                else v
                for v in value
            ]
        else:
            result[key] = value
    return result


def pii_detection_rate(
    samples: list[tuple[str, list[tuple[int, int, str]]]],
) -> float:
    """Compute detection rate against labelled PII spans.

    Args:
        samples: List of (text, expected_spans) where each expected span is
            (start, end, pii_type).

    Returns:
        Fraction of expected spans that were detected (overlap >= 50%).
    """
    if not samples:
        return 1.0

    total = 0
    detected = 0
    for text, expected in samples:
        matches = detect_pii(text)
        for start, end, _ in expected:
            total += 1
            exp_len = end - start
            for match in matches:
                overlap_start = max(match.start, start)
                overlap_end = min(match.end, end)
                overlap = max(0, overlap_end - overlap_start)
                if overlap / exp_len >= 0.5:
                    detected += 1
                    break
    return detected / total if total > 0 else 1.0
