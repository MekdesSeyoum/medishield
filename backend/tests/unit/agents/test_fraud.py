"""Unit tests for FraudAgent.

Four core cases:
  1. Clean claim     — no flags, score 0.0, risk LOW
  2. Duplicate       — same provider + patient + date in history, score 0.65, risk HIGH
  3. Amount outlier  — claim > 2σ above provider historical average, score 0.35, risk MEDIUM
  4. High-frequency  — provider > 5 claims in 7 days, score 0.30, risk MEDIUM

All tests inject a fixed reference_date (2024-03-20) and inline history so they
run without any file I/O and remain deterministic across time.
"""

from datetime import date
from uuid import uuid4

import pytest

from pipeline.agents.fraud import FraudAgent, _classify_risk
from shared.schemas.agent_io import FraudInput

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_REF = date(2024, 3, 20)

# Inline claim history — mirrors claim_history.json but kept in-process for
# test isolation.  Comments explain which test case each block serves.
_HISTORY: list[dict] = [
    # Provider 1111111111 — PAT-001 — two old claims, both outside the 30-day
    # duplicate window and 7-day frequency window (clean provider).
    {"claim_id": "H001", "patient_id": "PAT-001", "provider_npi": "1111111111", "claim_amount": 150.00, "service_date": "2024-01-05"},
    {"claim_id": "H002", "patient_id": "PAT-001", "provider_npi": "1111111111", "claim_amount": 175.00, "service_date": "2024-02-10"},

    # Provider 2222222222 — PAT-002 — recent claim that will match the
    # duplicate-detection test (same patient + provider + service_date).
    {"claim_id": "H003", "patient_id": "PAT-002", "provider_npi": "2222222222", "claim_amount": 300.00, "service_date": "2024-03-18"},

    # Provider 3333333333 — 5 historical claims used to compute μ and σ.
    # μ = 200, σ ≈ 14.58  →  2σ-threshold ≈ 229.15
    {"claim_id": "H004", "patient_id": "PAT-003", "provider_npi": "3333333333", "claim_amount": 190.00, "service_date": "2024-01-10"},
    {"claim_id": "H005", "patient_id": "PAT-003", "provider_npi": "3333333333", "claim_amount": 210.00, "service_date": "2024-01-20"},
    {"claim_id": "H006", "patient_id": "PAT-003", "provider_npi": "3333333333", "claim_amount": 185.00, "service_date": "2024-02-05"},
    {"claim_id": "H007", "patient_id": "PAT-003", "provider_npi": "3333333333", "claim_amount": 220.00, "service_date": "2024-02-15"},
    {"claim_id": "H008", "patient_id": "PAT-003", "provider_npi": "3333333333", "claim_amount": 195.00, "service_date": "2024-02-25"},

    # Provider 4444444444 — 6 different patients, all within 7 days of _REF →
    # high-frequency flag fires (6 > threshold of 5).
    {"claim_id": "H009", "patient_id": "PAT-004A", "provider_npi": "4444444444", "claim_amount": 200.00, "service_date": "2024-03-14"},
    {"claim_id": "H010", "patient_id": "PAT-004B", "provider_npi": "4444444444", "claim_amount": 200.00, "service_date": "2024-03-15"},
    {"claim_id": "H011", "patient_id": "PAT-004C", "provider_npi": "4444444444", "claim_amount": 200.00, "service_date": "2024-03-16"},
    {"claim_id": "H012", "patient_id": "PAT-004D", "provider_npi": "4444444444", "claim_amount": 200.00, "service_date": "2024-03-17"},
    {"claim_id": "H013", "patient_id": "PAT-004E", "provider_npi": "4444444444", "claim_amount": 200.00, "service_date": "2024-03-18"},
    {"claim_id": "H014", "patient_id": "PAT-004F", "provider_npi": "4444444444", "claim_amount": 200.00, "service_date": "2024-03-19"},
]


def _agent() -> FraudAgent:
    return FraudAgent(claim_history=_HISTORY, reference_date=_REF)


def _input(
    patient_id: str = "PAT-001",
    provider_npi: str = "1111111111",
    claim_amount: float = 160.0,
    service_date: str = "2024-03-20",
) -> FraudInput:
    return FraudInput(
        case_id=uuid4(),
        extracted_fields={"service_date": service_date, "cpt_codes": ["99213"]},
        patient_id=patient_id,
        provider_npi=provider_npi,
        claim_amount=claim_amount,
    )


# ---------------------------------------------------------------------------
# Case 1 — Clean claim
# ---------------------------------------------------------------------------


def test_clean_claim_score_is_zero() -> None:
    # PAT-001 / provider 1111111111 has no history in the 30-day window and
    # only 2 past claims (below _MIN_HISTORY_FOR_STATS=3), so no flags fire.
    result = _agent().run(_input())

    assert result.fraud_score == 0.0
    assert result.risk_level == "LOW"
    assert result.anomalies == []


def test_clean_claim_produces_no_anomalies() -> None:
    result = _agent().run(_input())

    assert len(result.anomalies) == 0


# ---------------------------------------------------------------------------
# Case 2 — Duplicate submission
# ---------------------------------------------------------------------------


def test_duplicate_claim_is_high_risk() -> None:
    # H003 in history: PAT-002 + 2222222222 + 2024-03-18
    result = _agent().run(
        _input(patient_id="PAT-002", provider_npi="2222222222",
               claim_amount=300.0, service_date="2024-03-18")
    )

    assert result.risk_level == "HIGH"
    assert result.fraud_score == pytest.approx(0.65, abs=1e-4)
    assert any("duplicate" in a.lower() for a in result.anomalies)


def test_duplicate_flag_contains_patient_and_provider() -> None:
    result = _agent().run(
        _input(patient_id="PAT-002", provider_npi="2222222222",
               claim_amount=300.0, service_date="2024-03-18")
    )

    assert any("PAT-002" in a and "2222222222" in a for a in result.anomalies)


def test_different_service_date_does_not_trigger_duplicate() -> None:
    result = _agent().run(
        _input(patient_id="PAT-002", provider_npi="2222222222",
               claim_amount=300.0, service_date="2024-03-19")
    )

    assert not any("duplicate" in a.lower() for a in result.anomalies)


def test_claim_outside_30_day_window_not_a_duplicate() -> None:
    # H001 is on 2024-01-05, well outside the 30-day window from 2024-03-20.
    result = _agent().run(
        _input(patient_id="PAT-001", provider_npi="1111111111",
               claim_amount=150.0, service_date="2024-01-05")
    )

    assert not any("duplicate" in a.lower() for a in result.anomalies)


# ---------------------------------------------------------------------------
# Case 3 — High-amount outlier
# ---------------------------------------------------------------------------


def test_amount_outlier_is_medium_risk() -> None:
    # Provider 3333333333: μ=200, σ≈14.58 → 2σ-threshold ≈ 229.15
    # $800 is far above the threshold.
    result = _agent().run(
        _input(patient_id="PAT-003-NEW", provider_npi="3333333333",
               claim_amount=800.0, service_date="2024-03-20")
    )

    assert result.risk_level == "MEDIUM"
    assert result.fraud_score == pytest.approx(0.35, abs=1e-4)
    assert any("2σ" in a or "σ" in a for a in result.anomalies)


def test_amount_outlier_message_includes_mean_and_sigma() -> None:
    result = _agent().run(
        _input(patient_id="PAT-003-NEW", provider_npi="3333333333",
               claim_amount=800.0, service_date="2024-03-20")
    )

    msg = result.anomalies[0]
    assert "mean=" in msg or "mean" in msg.lower()
    assert "σ" in msg


def test_amount_within_normal_range_not_flagged() -> None:
    # $205 < μ + 2σ (≈229), so no outlier flag.
    result = _agent().run(
        _input(patient_id="PAT-003-NEW", provider_npi="3333333333",
               claim_amount=205.0, service_date="2024-03-20")
    )

    assert not any("σ" in a for a in result.anomalies)


def test_insufficient_provider_history_skips_outlier_check() -> None:
    # Provider 1111111111 has only 2 historical claims < _MIN_HISTORY_FOR_STATS.
    result = _agent().run(
        _input(provider_npi="1111111111", claim_amount=99999.0)
    )

    assert not any("σ" in a for a in result.anomalies)


# ---------------------------------------------------------------------------
# Case 4 — High-frequency provider
# ---------------------------------------------------------------------------


def test_high_frequency_provider_is_medium_risk() -> None:
    # Provider 4444444444 has 6 claims in the past 7 days (H009–H014 → all ≥ 2024-03-13).
    result = _agent().run(
        _input(patient_id="PAT-NEW", provider_npi="4444444444",
               claim_amount=200.0, service_date="2024-03-20")
    )

    assert result.risk_level == "MEDIUM"
    assert result.fraud_score == pytest.approx(0.30, abs=1e-4)
    assert any("claims" in a.lower() or "frequency" in a.lower() for a in result.anomalies)


def test_high_frequency_message_includes_count_and_threshold() -> None:
    result = _agent().run(
        _input(patient_id="PAT-NEW", provider_npi="4444444444",
               claim_amount=200.0, service_date="2024-03-20")
    )

    msg = next(a for a in result.anomalies if "claims" in a.lower())
    assert "6" in msg   # actual recent count
    assert "5" in msg   # threshold


def test_provider_under_frequency_threshold_not_flagged() -> None:
    result = _agent().run(_input(provider_npi="1111111111"))

    assert not any("frequency" in a.lower() or "claims" in a.lower() for a in result.anomalies)


# ---------------------------------------------------------------------------
# Scoring and risk boundary tests
# ---------------------------------------------------------------------------


def test_fraud_score_capped_at_one_when_all_checks_fire() -> None:
    """0.65 + 0.35 + 0.30 = 1.30 → must be capped at 1.0."""
    # Build history that triggers all three checks for provider 9999999999.
    all_flags_history = [
        # Duplicate anchor
        {"claim_id": "X001", "patient_id": "PAT-X", "provider_npi": "9999999999", "claim_amount": 200.00, "service_date": "2024-03-18"},
        # Enough history for σ (μ=200, σ≈8.2 → 2σ-threshold ≈216)
        {"claim_id": "X002", "patient_id": "PAT-X1", "provider_npi": "9999999999", "claim_amount": 190.00, "service_date": "2024-01-01"},
        {"claim_id": "X003", "patient_id": "PAT-X2", "provider_npi": "9999999999", "claim_amount": 210.00, "service_date": "2024-01-02"},
        {"claim_id": "X004", "patient_id": "PAT-X3", "provider_npi": "9999999999", "claim_amount": 195.00, "service_date": "2024-01-03"},
        {"claim_id": "X005", "patient_id": "PAT-X4", "provider_npi": "9999999999", "claim_amount": 205.00, "service_date": "2024-01-04"},
        # High-frequency: X001 + X006–X010 = 6 within 7 days of 2024-03-20
        {"claim_id": "X006", "patient_id": "PAT-X5", "provider_npi": "9999999999", "claim_amount": 200.00, "service_date": "2024-03-14"},
        {"claim_id": "X007", "patient_id": "PAT-X6", "provider_npi": "9999999999", "claim_amount": 200.00, "service_date": "2024-03-15"},
        {"claim_id": "X008", "patient_id": "PAT-X7", "provider_npi": "9999999999", "claim_amount": 200.00, "service_date": "2024-03-16"},
        {"claim_id": "X009", "patient_id": "PAT-X8", "provider_npi": "9999999999", "claim_amount": 200.00, "service_date": "2024-03-17"},
        {"claim_id": "X010", "patient_id": "PAT-X9", "provider_npi": "9999999999", "claim_amount": 200.00, "service_date": "2024-03-19"},
    ]
    agent = FraudAgent(claim_history=all_flags_history, reference_date=_REF)
    result = agent.run(
        FraudInput(
            case_id=uuid4(),
            extracted_fields={"service_date": "2024-03-18"},
            patient_id="PAT-X",
            provider_npi="9999999999",
            claim_amount=2000.0,  # massive outlier
        )
    )

    assert result.fraud_score <= 1.0
    assert result.risk_level == "HIGH"
    assert len(result.anomalies) == 3


def test_risk_level_classification_boundaries() -> None:
    assert _classify_risk(0.00) == "LOW"
    assert _classify_risk(0.29) == "LOW"
    assert _classify_risk(0.30) == "MEDIUM"
    assert _classify_risk(0.60) == "MEDIUM"
    assert _classify_risk(0.61) == "HIGH"
    assert _classify_risk(1.00) == "HIGH"


def test_missing_service_date_skips_duplicate_check() -> None:
    result = _agent().run(
        FraudInput(
            case_id=uuid4(),
            extracted_fields={},          # no service_date key
            patient_id="PAT-002",
            provider_npi="2222222222",
            claim_amount=300.0,
        )
    )

    assert not any("duplicate" in a.lower() for a in result.anomalies)
