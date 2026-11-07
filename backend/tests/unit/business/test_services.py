"""Business services with in-memory fakes: no database, no scene file, no LLM."""

from typing import Any, Dict, List, Optional

import pytest

from business.errors import NotFoundError, RouteNotFoundError
from business.services import CopilotService, MaintenanceService, NavigationService, SceneService

ASSETS = [
    {"asset_id": "ASSET-017", "tag": "P-005", "asset_class": "PROCESS_PUMP", "area_id": "AREA-03", "area_name": "Utility Island", "criticality": "A - production critical"},
    {"asset_id": "ASSET-001", "tag": "CV-001", "asset_class": "CONTROL_VALVE", "area_id": "AREA-03", "area_name": "Utility Island", "criticality": "B - important"},
]
STATES = {
    "ASSET-017": {"asset_id": "ASSET-017", "health_score": 44.0, "condition_state": "attention_required", "issue_code": "FOULING",
                  "issue_summary": "Efficiency loss", "urgency": "high", "model_confidence": 0.91,
                  "recommended_next_check": "inspect hydraulic path", "knowledge_doc_id": "DOC-PROCESS_PUMP-CORE"},
    "ASSET-001": {"asset_id": "ASSET-001", "health_score": 96.0, "condition_state": "healthy", "issue_code": "NORMAL",
                  "urgency": "routine", "model_confidence": 0.89, "knowledge_doc_id": "DOC-CONTROL_VALVE-CORE"},
}


class FakeRepository:
    def find(self, identifier: str):
        key = identifier.lower()
        return next((a for a in ASSETS if key in (a["asset_id"].lower(), a["tag"].lower())), None)

    def list(self, *args, **kwargs):
        return list(ASSETS)

    def states(self, asset_ids=None):
        return {k: v for k, v in STATES.items() if asset_ids is None or k in list(asset_ids)}

    def recent_telemetry(self, asset_id: str, limit: int):
        flow = [80.0 + (i % 3) * 0.2 for i in range(96)] + [70.0 + (i % 3) * 0.2 for i in range(48)]
        return [{"timestamp": f"2026-10-05T{i:04d}", "process_flow_pct": v} for i, v in enumerate(flow)]

    def events(self, asset_id, limit, *args):
        return [{"event_id": "EVT-00037", "timestamp": "2026-10-07", "event_type": "DIAGNOSTIC_ALERT",
                 "event_code": "FOULING", "severity": "high", "description": "Fouling-like signature."}]

    def work_orders(self, asset_id, limit):
        return []

    def documents(self, doc_ids=(), scopes=()):
        return [{"doc_id": "DOC-FIELD-SAFETY", "title": "Safety", "scope": "ALL", "content": "Use LOTO."}]

    def service_cases(self, asset_class):
        return [{"case_id": "CASE-025", "historical_issue_code": "FOULING", "historical_interpretation": "Fouling",
                 "recommended_next_check": "inspect hydraulic path", "safe_evidence_workflow": "Confirm identity."}]

    def data_quality(self, asset_id):
        return []


class FakeScene:
    target_asset_id = "ASSET-017"

    def find_frame(self, identifier: str) -> Optional[Dict[str, Any]]:
        if identifier == "ASSET-017":
            return {"asset_id": "ASSET-017", "scene_id": "OBJ-010", "mapping_confidence": 0.85}
        return None

    def get_navigation_path(self, target_id=None, start=None):
        if target_id == "missing":
            raise KeyError(target_id)

        class RouteNotFound(Exception):
            pass

        raise RouteNotFound(target_id)


class FakeLlm:
    name = "fake-llm"
    is_available = True

    def __init__(self, cited: List[str]):
        self.cited = cited

    def complete_json(self, prompt: str):
        return {"answer": "Flow dropped [EVT-00037].", "recommended_actions": ["Inspect strainer."], "cited_ids": self.cited}


def test_copilot_flags_drift_and_cites_only_evidence():
    result = CopilotService(FakeRepository(), FakeScene()).diagnose("P-005")
    assert result["tag"] == "P-005"
    assert any("Process flow" in e for e in result["multivariate_evidence"])
    assert "EVT-00037" in result["evidence_citations"]
    assert result["grounded_mode"] == "deterministic-evidence-engine"


def test_llm_answer_accepted_only_with_known_citations():
    good = CopilotService(FakeRepository(), FakeScene(), FakeLlm(["EVT-00037"])).diagnose("P-005", "why?")
    assert good["answer"].startswith("Flow dropped")
    assert "citations verified" in good["grounded_mode"]
    bad = CopilotService(FakeRepository(), FakeScene(), FakeLlm(["EVT-99999"])).diagnose("P-005", "why?")
    assert bad["answer"] is None
    assert bad["grounded_mode"] == "deterministic-evidence-engine"


def test_unknown_asset_is_not_found():
    with pytest.raises(NotFoundError):
        CopilotService(FakeRepository(), FakeScene()).diagnose("X-999")


def test_navigation_errors_become_domain_errors():
    service = NavigationService(FakeScene())
    with pytest.raises(NotFoundError):
        service.path("missing")
    with pytest.raises(RouteNotFoundError):
        service.path("ASSET-001")


def test_maintenance_priorities_rank_faulty_critical_assets_first():
    repo = FakeRepository()
    ranked = MaintenanceService(repo, SceneService(FakeScene(), repo)).priorities(limit=5)
    assert [r["asset_id"] for r in ranked] == ["ASSET-017"]  # healthy assets excluded
    assert ranked[0]["rank"] == 1
    assert ranked[0]["scene_object_id"] == "OBJ-010"
