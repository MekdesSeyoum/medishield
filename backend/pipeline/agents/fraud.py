import json
import statistics
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from shared.schemas.agent_io import FraudInput, FraudOutput

_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "claim_history.json"

# Anomaly weights — additive, capped at 1.0
_W_DUPLICATE = 0.65
_W_AMOUNT_OUTLIER = 0.35
_W_HIGH_FREQUENCY = 0.30

# Rule thresholds
_DUPLICATE_WINDOW_DAYS = 30
_AMOUNT_SIGMA = 2.0
_MIN_HISTORY_FOR_STATS = 3  # need at least this many past claims to compute σ
_HIGH_FREQ_THRESHOLD = 5    # > N claims triggers the flag
_HIGH_FREQ_WINDOW_DAYS = 7


def _classify_risk(score: float) -> Literal["LOW", "MEDIUM", "HIGH"]:
    if score < 0.3:
        return "LOW"
    if score <= 0.6:
        return "MEDIUM"
    return "HIGH"


class FraudAgent:
    """Rules-based fraud detection.

    No LLM required — all checks are deterministic against claim history.
    Designed as an independent LangGraph node; wire in via fraud_node().
    """

    def __init__(
        self,
        claim_history: list[dict] | None = None,
        reference_date: date | None = None,
    ) -> None:
        if claim_history is not None:
            self._history = claim_history
        else:
            with open(_FIXTURE_PATH) as f:
                self._history: list[dict] = json.load(f)["claims"]

        # Injecting reference_date makes the agent deterministic in tests.
        self._ref = reference_date or date.today()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self, input: FraudInput) -> FraudOutput:
        anomalies: list[str] = []
        score = 0.0

        svc_date_str: str = input.extracted_fields.get("service_date", "")
        svc_date: date | None = (
            date.fromisoformat(svc_date_str) if svc_date_str else None
        )

        # --- Check 1: duplicate submission ---
        if svc_date and self._check_duplicate(
            input.patient_id, input.provider_npi, svc_date
        ):
            anomalies.append(
                f"Duplicate submission: provider {input.provider_npi} already has a "
                f"claim for patient {input.patient_id} on {svc_date_str} "
                f"(within {_DUPLICATE_WINDOW_DAYS}-day window)"
            )
            score += _W_DUPLICATE

        # --- Check 2: claim amount > 2σ above provider historical average ---
        outlier = self._check_amount_outlier(input.provider_npi, input.claim_amount)
        if outlier:
            mean, stdev = outlier
            anomalies.append(
                f"Claim amount ${input.claim_amount:.2f} exceeds 2σ above provider "
                f"{input.provider_npi} historical average "
                f"(mean=${mean:.2f}, σ=${stdev:.2f})"
            )
            score += _W_AMOUNT_OUTLIER

        # --- Check 3: high-frequency submissions from same provider ---
        freq_count = self._check_high_frequency(input.provider_npi)
        if freq_count is not None:
            anomalies.append(
                f"Provider {input.provider_npi} submitted {freq_count} claims in the "
                f"past {_HIGH_FREQ_WINDOW_DAYS} days (threshold: {_HIGH_FREQ_THRESHOLD})"
            )
            score += _W_HIGH_FREQUENCY

        capped = min(score, 1.0)

        return FraudOutput(
            fraud_score=round(capped, 4),
            anomalies=anomalies,
            risk_level=_classify_risk(capped),
        )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_duplicate(
        self, patient_id: str, provider_npi: str, svc_date: date
    ) -> bool:
        """Return True if history contains a same-patient+provider+date claim within
        the duplicate window."""
        cutoff = self._ref - timedelta(days=_DUPLICATE_WINDOW_DAYS)
        return any(
            c["patient_id"] == patient_id
            and c["provider_npi"] == provider_npi
            and date.fromisoformat(c["service_date"]) == svc_date
            and cutoff <= date.fromisoformat(c["service_date"]) <= self._ref
            for c in self._history
        )

    def _check_amount_outlier(
        self, provider_npi: str, claim_amount: float
    ) -> tuple[float, float] | None:
        """Return (mean, stdev) if claim_amount > mean + 2σ, else None.

        Returns None when there is insufficient history to compute statistics.
        """
        amounts = [
            c["claim_amount"]
            for c in self._history
            if c["provider_npi"] == provider_npi
        ]
        if len(amounts) < _MIN_HISTORY_FOR_STATS:
            return None
        mean = statistics.mean(amounts)
        stdev = statistics.stdev(amounts)
        if stdev == 0:
            return None
        if claim_amount > mean + _AMOUNT_SIGMA * stdev:
            return (mean, stdev)
        return None

    def _check_high_frequency(self, provider_npi: str) -> int | None:
        """Return the recent claim count if it exceeds _HIGH_FREQ_THRESHOLD, else None."""
        cutoff = self._ref - timedelta(days=_HIGH_FREQ_WINDOW_DAYS)
        recent = [
            c
            for c in self._history
            if c["provider_npi"] == provider_npi
            and date.fromisoformat(c["service_date"]) >= cutoff
        ]
        count = len(recent)
        return count if count > _HIGH_FREQ_THRESHOLD else None


def fraud_node(state: dict) -> dict:
    """LangGraph node: runs FraudAgent and writes fraud_result into graph state."""
    agent = FraudAgent()
    output = agent.run(
        FraudInput(
            case_id=state["case_id"],
            extracted_fields=state.get("extracted_fields", {}),
            patient_id=state["patient_id"],
            provider_npi=state["provider_npi"],
            claim_amount=state["claim_amount"],
        )
    )
    return {"fraud_result": output.model_dump()}
