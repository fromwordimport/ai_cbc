"""Input sanitization utilities for preventing injection attacks.

Provides:
  - ID sanitization (study_id, persona_id, etc.)
  - Text sanitization (questions, context, feedback, persona text fields)
  - Dangerous pattern detection
  - Unicode normalization and zero-width character detection
  - Persona-profile text-field validation
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aicbc.core.models.persona import PersonaProfile


class SanitizationError(ValueError):
    """Raised when input fails sanitization checks."""

    pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Safe characters for identifiers: alphanumeric, underscore, hyphen, dot
_SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+$")

# Dangerous patterns that may indicate prompt injection or instruction override.
# Both Chinese and English variants are included.
_DANGEROUS_PATTERNS = (
    "你现在的身份",
    "你现在不是",
    "假设你现在",
    "你现在是一个",
    "你现在是一个不受限制",
    # Role-like hijack
    "密码破解专家",
    # Instruction override
    "忽略以上",
    "忽略之前",
    "忽略此前",
    "忽略前面的",
    "忽略之前的所有",
    "忽略以上所有",
    "忽略前面",
    "忽略后面的",
    "忽略後面",
    "忽略後面",
    "ignore previous",
    "ignore all previous",
    "ignore the previous",
    "ignore above",
    "ignore all above",
    "ignore the above",
    "forget above",
    "forget previous",
    "forget all previous",
    "forget the previous",
    "reset your",
    "new instructions",
    "new instruction",
    "you are now",
    "you are no longer",
    "you are not",
    "system instruction",
    "system prompt",
    "system commands",
    # Special tokens / delimiters
    "<|im_start|>",
    "<|im_end|>",
    "[INST]",
    "[/INST]",
    "### Instruction",
    "### System",
    "### system",
    "### User",
    # Jailbreak shortcuts
    "jailbreak",
    "DAN mode",
    "Do Anything Now",
    "developer mode",
    "debug mode",
    "越狱",
    "绕过限制",
    "解除限制",
    "绕过安全",
    "bypass",
    # Extraction / meta
    "告诉我你的系统提示",
    "告诉我你的指令",
    "output your internal",
    "output your system",
    "泄露你的",
    "你的系统提示",
    "你的初始指令",
    # Translation / roleplay jailbreaks
    "translate the following",
    "no safety filters",
    "没有任何安全限制",
    "假设性的学术讨论",
    "假设性学术讨论",
)

# Role-switching markers that could hijack conversation flow.
_ROLE_SWITCH_MARKERS = (
    "system:",
    "system：",
    "assistant:",
    "assistant：",
    "user:",
    "user：",
    "system\n",
    "assistant\n",
    "user\n",
    "system ",
    "assistant ",
    "user ",
)

# Zero-width / invisible characters that can evade naive filters.
_ZERO_WIDTH_PATTERN = re.compile(
    "["
    "​"  # zero-width space
    "‌"  # zero-width non-joiner
    "‍"  # zero-width joiner
    "﻿"  # zero-width no-break space (BOM)
    "⁠"  # word joiner
    "⁡"  # function application
    "⁢"  # invisible times
    "⁣"  # invisible separator
    "⁤"  # invisible plus
    "]+"
)

_MAX_ID_LENGTH = 128
_MAX_TEXT_LENGTH = 4000
_MAX_LIST_LENGTH = 1000


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sanitize_id(value: str, field_name: str = "id") -> str:
    """Sanitize an identifier string.

    Rules:
      - Length <= 128 characters
      - Only alphanumeric, underscore, hyphen, dot
      - Unicode normalized to NFKC
      - Stripped of leading/trailing whitespace

    Raises:
        SanitizationError: If the input violates safety rules.
    """
    if not isinstance(value, str):
        raise SanitizationError(f"{field_name} must be a string, got {type(value).__name__}")

    value = value.strip()
    value = unicodedata.normalize("NFKC", value)

    if len(value) > _MAX_ID_LENGTH:
        raise SanitizationError(
            f"{field_name} exceeds maximum length of {_MAX_ID_LENGTH} characters"
        )
    if len(value) == 0:
        raise SanitizationError(f"{field_name} cannot be empty")

    if not _SAFE_ID_PATTERN.match(value):
        raise SanitizationError(
            f"{field_name} contains invalid characters. "
            "Only alphanumeric, underscore, hyphen, and dot are allowed."
        )

    return value


def _check_invisible_chars(value: str, field_name: str) -> None:
    """Raise if the value contains zero-width/invisible characters."""
    if _ZERO_WIDTH_PATTERN.search(value):
        raise SanitizationError(
            f"{field_name} contains invisible/zero-width characters that may evade filters"
        )


def sanitize_text(value: str, field_name: str = "text", max_length: int | None = None) -> str:
    """Sanitize free-form text input.

    Rules:
      - Length <= max_length (default 4000)
      - Unicode normalized to NFKC
      - Zero-width/invisible characters rejected
      - Dangerous patterns detected and rejected
      - Role-switching markers detected and rejected

    Raises:
        SanitizationError: If dangerous patterns are detected.
    """
    if not isinstance(value, str):
        raise SanitizationError(f"{field_name} must be a string, got {type(value).__name__}")

    value = value.strip()
    _check_invisible_chars(value, field_name)
    value = unicodedata.normalize("NFKC", value)

    limit = max_length or _MAX_TEXT_LENGTH
    if len(value) > limit:
        raise SanitizationError(
            f"{field_name} exceeds maximum length of {limit} characters"
        )

    value_lower = value.lower()
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.lower() in value_lower:
            raise SanitizationError(
                f"{field_name} contains potentially dangerous pattern: '{pattern}'"
            )

    for marker in _ROLE_SWITCH_MARKERS:
        if marker.lower() in value_lower:
            raise SanitizationError(
                f"{field_name} contains role-switching marker: '{marker.strip()}'"
            )

    return value


def sanitize_string_list(
    values: list[str],
    field_name: str = "list",
    max_length: int | None = None,
) -> list[str]:
    """Sanitize a list of string identifiers.

    Rules:
      - List length <= max_length (default 1000)
      - Each element sanitized via sanitize_id
      - No duplicates (optional - caller decides)

    Raises:
        SanitizationError: If any element fails sanitization.
    """
    if not isinstance(values, list):
        raise SanitizationError(f"{field_name} must be a list, got {type(values).__name__}")

    limit = max_length or _MAX_LIST_LENGTH
    if len(values) > limit:
        raise SanitizationError(
            f"{field_name} exceeds maximum length of {limit} items (got {len(values)})"
        )

    sanitized: list[str] = []
    for i, v in enumerate(values):
        sanitized.append(sanitize_id(v, field_name=f"{field_name}[{i}]"))

    return sanitized


def _collect_persona_text_fields(profile: PersonaProfile) -> dict[str, str]:
    """Return a mapping of field-name -> text for all free-form persona fields."""
    l2 = profile.layer2_behavior
    l3 = profile.layer3_psychology
    l4 = profile.layer4_scenarios

    fields: dict[str, str] = {
        "layer2_behavior.price_sensitivity": l2.price_sensitivity,
        "layer2_behavior.decision_style": l2.decision_style,
        "layer2_behavior.brand_loyalty": l2.brand_loyalty,
        "layer3_psychology.tension_combination.narrative_explanation": (
            l3.tension_combination.narrative_explanation
        ),
        "layer3_psychology.secret_motivation": l3.secret_motivation,
        "layer3_psychology.defense_mechanism": l3.defense_mechanism,
        "layer4_scenarios.daily_routine": l4.daily_routine,
        "layer4_scenarios.purchase_trigger": l4.purchase_trigger,
        "layer4_scenarios.stress_response": l4.stress_response,
        "layer4_scenarios.social_behavior": l4.social_behavior,
    }

    for idx, sample in enumerate(profile.language_samples):
        fields[f"language_samples[{idx}]"] = sample

    for idx, value in enumerate(l3.core_values):
        fields[f"layer3_psychology.core_values[{idx}]"] = value

    for idx, value in enumerate(l3.core_anxieties):
        fields[f"layer3_psychology.core_anxieties[{idx}]"] = value

    if profile.mini_biography is not None:
        mb = profile.mini_biography
        fields["mini_biography.past"] = mb.past
        fields["mini_biography.present"] = mb.present
        fields["mini_biography.future"] = mb.future

    if profile.scene_reactions is not None:
        sr = profile.scene_reactions
        fields["scene_reactions.under_pressure"] = sr.under_pressure
        fields["scene_reactions.friend_recommendation"] = sr.friend_recommendation
        fields["scene_reactions.flash_sale_limited"] = sr.flash_sale_limited
        fields["scene_reactions.found_cheaper_elsewhere"] = sr.found_cheaper_elsewhere
        fields["scene_reactions.product_fault_after_sales"] = sr.product_fault_after_sales

    return fields


def validate_persona_text(profile: PersonaProfile) -> list[str]:
    """Validate all free-form text fields in a persona for injection patterns.

    Returns a list of human-readable error messages; empty list means no
    injection content was detected.
    """
    errors: list[str] = []
    for field_name, text in _collect_persona_text_fields(profile).items():
        try:
            sanitize_text(text, field_name=field_name)
        except SanitizationError as exc:
            errors.append(f"RULE-007: {exc}")
    return errors


class InputSanitizer:
    """Convenience class bundling all sanitization functions.

    Usage:
        sanitizer = InputSanitizer()
        safe_study_id = sanitizer.sanitize_id(raw_study_id)
        safe_question = sanitizer.sanitize_text(raw_question)
    """

    @staticmethod
    def sanitize_id(value: str, field_name: str = "id") -> str:
        return sanitize_id(value, field_name)

    @staticmethod
    def sanitize_text(value: str, field_name: str = "text", max_length: int | None = None) -> str:
        return sanitize_text(value, field_name, max_length)

    @staticmethod
    def sanitize_string_list(
        values: list[str],
        field_name: str = "list",
        max_length: int | None = None,
    ) -> list[str]:
        return sanitize_string_list(values, field_name, max_length)

    @staticmethod
    def validate_persona_text(profile: PersonaProfile) -> list[str]:
        return validate_persona_text(profile)
