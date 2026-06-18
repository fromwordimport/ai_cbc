"""Tests for PII detection and redaction utilities."""

from __future__ import annotations

import pytest

from aicbc.core.privacy import (
    detect_pii,
    pii_detection_rate,
    redact_dict,
    redact_pii,
)


class TestDetectPII:
    def test_detect_mobile_phone(self):
        text = "请联系我，手机号是13800138000。"
        matches = detect_pii(text)
        assert len(matches) == 1
        assert matches[0].pii_type == "mobile_phone"
        assert matches[0].value == "13800138000"

    def test_detect_id_card(self):
        text = "身份证号：110101199001011234"
        matches = detect_pii(text)
        assert any(m.pii_type == "id_card" for m in matches)
        id_match = next(m for m in matches if m.pii_type == "id_card")
        assert id_match.value == "110101199001011234"

    def test_detect_email(self):
        text = "发送邮件至 user@example.com 谢谢"
        matches = detect_pii(text)
        assert any(m.pii_type == "email" for m in matches)
        assert any(m.value == "user@example.com" for m in matches)

    def test_detect_bank_card(self):
        text = "银行卡号 6222021234567890123 已绑定"
        matches = detect_pii(text)
        assert any(m.pii_type == "bank_card" for m in matches)

    def test_detect_name(self):
        text = "联系人：张三，电话 13800138001"
        matches = detect_pii(text)
        assert any(m.pii_type == "name" for m in matches)
        name_match = next(m for m in matches if m.pii_type == "name")
        assert name_match.value == "张三"

    def test_overlapping_matches_prefer_longer(self):
        # 15-digit ID inside a longer numeric string should not be double-counted.
        text = "卡号 1234567890123456 和身份证 110101199001011234"
        matches = detect_pii(text)
        types = [m.pii_type for m in matches]
        assert types.count("bank_card") == 1
        assert types.count("id_card") == 1


class TestRedactPII:
    def test_redact_mobile_phone_irreversible(self):
        text = "电话：13800138000"
        redacted = redact_pii(text, irreversible=True)
        assert "13800138000" not in redacted
        assert "[REDACTED:mobile_phone:" in redacted

    def test_redact_mobile_phone_mask(self):
        text = "电话：13800138000"
        redacted = redact_pii(text, irreversible=False)
        assert redacted == "电话：138****8000"

    def test_redact_email_mask(self):
        text = "邮箱：alice@example.com"
        redacted = redact_pii(text, irreversible=False)
        assert redacted == "邮箱：a****@example.com"

    def test_redaction_is_irreversible(self):
        original = "联系 13800138000 或 110101199001011234"
        redacted = redact_pii(original, irreversible=True)
        # Original values must not be recoverable from the redacted text.
        assert "13800138000" not in redacted
        assert "110101199001011234" not in redacted
        # Re-redacting should be idempotent.
        assert redact_pii(redacted, irreversible=True) == redacted

    def test_no_pii_unchanged(self):
        text = "This is a normal sentence without PII."
        assert redact_pii(text) == text


class TestRedactDict:
    def test_redact_nested_strings(self):
        data = {
            "name": "张三",
            "contact": "13800138000",
            "nested": {"email": "a@b.com"},
            "count": 42,
        }
        redacted = redact_dict(data)
        assert "[REDACTED:name:" in redacted["name"]
        assert "13800138000" not in redacted["contact"]
        assert "a@b.com" not in redacted["nested"]["email"]
        assert redacted["count"] == 42

    def test_redact_list_values(self):
        data = {"contacts": ["13800138000", "13900139000"]}
        redacted = redact_dict(data)
        assert all("13800138000" not in v for v in redacted["contacts"])
        assert all("13900139000" not in v for v in redacted["contacts"])


class TestPIIDetectionRate:
    def test_perfect_detection_rate(self):
        samples = [
            ("电话 13800138000", [(3, 14, "mobile_phone")]),
            ("身份证 110101199001011234", [(4, 22, "id_card")]),
        ]
        assert pii_detection_rate(samples) == 1.0

    def test_partial_detection_rate(self):
        samples = [
            ("电话 13800138000", [(3, 14, "mobile_phone")]),
            ("无 PII 文本", [(0, 5, "name")]),  # false expected span
        ]
        assert pii_detection_rate(samples) == 0.5


class TestPIIRobustness:
    @pytest.mark.parametrize(
        "phone",
        [
            "13800138000",
            "15912345678",
            "19987654321",
        ],
    )
    def test_multiple_mobile_prefixes(self, phone):
        assert any(
            m.pii_type == "mobile_phone" and m.value == phone
            for m in detect_pii(f"号码{phone}结束")
        )

    def test_mobile_not_detected_in_long_number(self):
        # 20-digit number should not be detected as mobile phone.
        text = "编号 12345678901234567890"
        matches = detect_pii(text)
        assert not any(m.pii_type == "mobile_phone" for m in matches)
