"""Copilot grounding tests: drift detection, verified citations and confidence penalties."""

from fastapi.testclient import TestClient

from api.server import app
from business.services.copilot_service import detect_drift

client = TestClient(app)


def _series(values):
    return [{"timestamp": f"2026-10-05T{i:04d}", "vibration_mm_s": v} for i, v in enumerate(values)]


def test_detect_drift_flags_recent_shift_only():
    steady = [2.0 + 0.05 * (i % 3) for i in range(30)]
    assert detect_drift(_series(steady)) == []
    drift = detect_drift(_series(steady[:20] + [3.5] * 10))
    assert drift[0]["signal"] == "vibration_mm_s"
    assert drift[0]["t_score"] > 3
    assert drift[0]["change_pct"] > 50


def test_target_diagnosis_cites_only_existing_evidence():
    res = client.post("/api/copilot/query", json={"asset_id": "P-005", "query": "What should I inspect first?"})
    assert res.status_code == 200, res.text
    diag = res.json()
    assert diag["issue_code"] == "FOULING"
    assert diag["diagnosis"].startswith("Hypothesis:")
    ids = set(diag["evidence_citations"])
    assert {"DOC-FIELD-SAFETY", "DOC-PROCESS_PUMP-CORE"} <= ids
    assert any(i.startswith("EVT-") for i in ids)
    assert "TEL-P-005-process_flow_pct" in ids  # fouling: sustained flow loss
    assert any(i.startswith("CASE-") for i in ids)
    assert any(i.startswith("DQ-") for i in ids)
    # 9 data-quality issues on P-005 must lower confidence below the raw model confidence (0.91)
    assert diag["confidence_score"] < 0.91


def test_unknown_asset_is_404():
    assert client.post("/api/copilot/query", json={"asset_id": "NOPE-999"}).status_code == 404


def test_copilot_auto_resolves_navigate_action():
    res = client.post("/api/copilot/query", json={"query": "Move robot to the faulty pump"})
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["action"] == "navigate"
    assert payload["tag"] == "P-005"
    assert payload["target_asset_id"] == "ASSET-017"


def test_copilot_auto_resolves_select_action():
    res = client.post("/api/copilot/query", json={"query": "Select the worst problem"})
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["action"] == "select"
    assert payload["tag"] == "P-005"
    assert payload["target_asset_id"] == "ASSET-017"

