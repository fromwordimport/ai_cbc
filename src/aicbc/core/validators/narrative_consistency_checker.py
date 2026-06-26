"""NarrativeConsistencyChecker — checks whether the mini-biography explains key tags."""

from __future__ import annotations

from dataclasses import dataclass, field

from aicbc.core.models.persona import PersonaProfile


@dataclass
class NarrativeConsistencyResult:
    """Result of checking narrative-tag consistency."""

    unexplained_tags: list[str] = field(default_factory=list)
    contradiction_score: float = 0.0


class NarrativeConsistencyChecker:
    """Check that key behavioral tags are explained by the mini-biography."""

    def check(self, persona: PersonaProfile) -> NarrativeConsistencyResult:
        """Return tags that appear in layers but lack support in the biography."""
        if not persona.mini_biography:
            return NarrativeConsistencyResult(
                unexplained_tags=["mini_biography_missing"],
                contradiction_score=1.0,
            )

        bio_text = " ".join(
            [
                persona.mini_biography.past,
                persona.mini_biography.present,
                persona.mini_biography.future,
            ]
        )

        key_tags: list[str] = []
        l2 = persona.layer2_behavior
        if l2.decision_style:
            key_tags.append(l2.decision_style)
        if l2.price_sensitivity:
            key_tags.append(l2.price_sensitivity)

        l3 = persona.layer3_psychology
        key_tags.extend(l3.tension_combination.labels)

        unexplained: list[str] = []
        for tag in key_tags:
            # Simple substring check; upgrade to embedding similarity in future.
            if tag and tag not in bio_text:
                unexplained.append(tag)

        score = min(1.0, len(unexplained) / max(len(key_tags), 1))
        return NarrativeConsistencyResult(
            unexplained_tags=unexplained,
            contradiction_score=round(score, 2),
        )
