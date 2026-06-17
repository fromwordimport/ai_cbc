"""Market share simulator based on estimated utility coefficients.

Predicts market shares for competing product scenarios using
the Logit choice rule or First-Choice rule.

TODO(NLScenarioParser): Implement natural-language-to-structured-scenario parser.
  - Defined in design doc §6.2 / §7.2: converts user input like "华为2999 vs 小米3999"
    into structured ProductScenario JSON using LLM.
  - Deferred to Phase 3 (post-MVP). Current workaround: use the form-based scenario
    editor in the MarketSimulator frontend page.
  - When implemented, use LLMClient.generate_json() with attribute definitions
    to produce list[ProductScenario].
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from aicbc.analysis.preprocessing import get_feature_columns
from aicbc.questionnaire.design.effects_coding import encode_profile
from aicbc.questionnaire.models import Attribute


class MarketSimulator:
    """Simulate market shares from individual utility estimates."""

    def __init__(
        self,
        individual_utilities: pd.DataFrame,
        attributes: list[Attribute],
    ) -> None:
        self.util = individual_utilities
        self.attributes = attributes
        self.feature_cols = list(individual_utilities.columns)

        # Verify column order matches attribute encoding order
        expected_cols = get_feature_columns(attributes)
        if list(individual_utilities.columns) != expected_cols:
            raise ValueError(
                f"Utility column order mismatch.\n"
                f"  Expected ({len(expected_cols)}): {expected_cols}\n"
                f"  Got      ({len(self.feature_cols)}): {self.feature_cols}\n"
                f"  The HB model's feature columns must match the attribute "
                f"  encoding order of MarketSimulator.attributes."
            )

    def simulate_share(
        self,
        scenarios: list[dict[str, object]],
        *,
        rule: str = "logit",
        include_none: bool = True,
        none_utility: float = 0.0,
        segment_filter: str | None = None,
    ) -> pd.DataFrame:
        """Simulate market shares for given product scenarios.

        Args:
            scenarios: List of product configurations, each a dict of
                {attribute_id: level_value}.
            rule: "logit" or "first_choice".
            include_none: Whether to include a "none" option.
            none_utility: Utility of the "none" option.
            segment_filter: Optional segment name to filter respondents.

        Returns:
            DataFrame with columns: name, predicted_share, share_ci_95_lower, share_ci_95_upper.
        """
        import numpy as np

        utilities = self._compute_utilities(scenarios, segment_filter)

        if include_none:
            none_col = np.full((utilities.shape[0], 1), none_utility)
            utilities = np.hstack([utilities, none_col])

        if rule == "logit":
            shares = self._logit_rule(utilities)
        elif rule == "first_choice":
            shares = self._first_choice_rule(utilities)
        else:
            raise ValueError(f"Unknown rule: {rule}")

        scenario_names = [s["name"] for s in scenarios]
        if include_none:
            scenario_names.append("none")

        import pandas as pd

        return pd.DataFrame(
            {
                "name": scenario_names,
                "predicted_share": shares.mean(axis=0),
                "share_std": shares.std(axis=0, ddof=1),
                "share_ci_95_lower": np.percentile(shares, 2.5, axis=0),
                "share_ci_95_upper": np.percentile(shares, 97.5, axis=0),
            }
        )

    def _compute_utilities(
        self,
        scenarios: list[dict[str, object]],
        segment_filter: str | None = None,
    ) -> np.ndarray:
        """Compute utility matrix (n_resp x n_scenarios)."""
        # Filter by segment if specified
        util = self.util
        if segment_filter is not None:
            # Note: segment info would need to be stored alongside utilities
            # For now, use all respondents
            pass

        # Build design matrix for scenarios (n_scenarios x n_features)
        scenario_matrix = self._build_scenario_matrix(scenarios)

        # Compute utilities: util (n_resp x n_features) @ scenario.T (n_features x n_scenarios)
        # → result (n_resp x n_scenarios)
        return util.values @ scenario_matrix.T

    def _build_scenario_matrix(
        self,
        scenarios: list[dict[str, object]],
    ) -> np.ndarray:
        """Convert scenario configs to design matrix.

        Raises:
            ValueError: If a scenario profile is invalid (missing attribute
                or unrecognised level value).
        """
        import numpy as np

        rows = []
        for i, scenario in enumerate(scenarios):
            # Remove "name" key if present
            profile = {k: v for k, v in scenario.items() if k != "name"}
            try:
                encoded = encode_profile(profile, self.attributes)
            except (ValueError, KeyError) as exc:
                raise ValueError(f"Scenario[{i}] '{scenario.get('name', '?')}': {exc}") from exc
            rows.append(encoded)
        return np.array(rows)

    @staticmethod
    def _logit_rule(utilities: np.ndarray) -> np.ndarray:
        """Logit choice rule: probability = softmax(utility)."""
        import numpy as np

        # Numerically stable softmax
        u = utilities - np.max(utilities, axis=1, keepdims=True)
        exp_u = np.exp(u)
        total = np.sum(exp_u, axis=1, keepdims=True)
        return exp_u / total

    @staticmethod
    def _first_choice_rule(utilities: np.ndarray) -> np.ndarray:
        """First choice rule: deterministic max utility."""
        import numpy as np

        choices = np.argmax(utilities, axis=1)
        n = utilities.shape[1]
        shares = np.zeros((len(choices), n))
        shares[np.arange(len(choices)), choices] = 1.0
        return shares

    def sensitivity_analysis(
        self,
        base_scenario: dict[str, object],
        attribute: str,
        values: list[float],
        competitors: list[dict[str, object]] | None = None,
    ) -> pd.DataFrame:
        """Run sensitivity analysis by varying one attribute.

        Args:
            base_scenario: Base product configuration.
            attribute: Attribute to vary.
            values: List of attribute values to test.
            competitors: Optional competing products.

        Returns:
            DataFrame with attribute value and predicted share.
        """
        results = []
        for value in values:
            scenario = base_scenario.copy()
            scenario[attribute] = value
            scenarios = [scenario]
            if competitors:
                scenarios.extend(competitors)

            shares = self.simulate_share(scenarios, include_none=False)
            base_share = shares[shares["name"] == base_scenario["name"]]["predicted_share"].values[
                0
            ]
            results.append(
                {
                    attribute: value,
                    "predicted_share": base_share,
                }
            )

        import pandas as pd

        return pd.DataFrame(results)
