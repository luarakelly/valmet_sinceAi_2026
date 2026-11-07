"""Copilot question routing, Gemini citation retry and briefing narration (Gemini stubbed)."""

import pytest

from app.metaverse.copilot import FieldServiceCopilot, classify_intent

ALLOWED = ["DOC-FIELD-SAFETY", "EVT-00001"]
RESULT = {
    "evidence_citations": ALLOWED,
    "tag": "P-005",
    "asset_class": "PROCESS_PUMP",
    "condition_state": "attention_required",
    "health_score": 44,
    "issue_code": "FOULING",
    "diagnosis": "Hypothesis: fouling.",
    "citations": [],
    "recommended_actions": ["Confirm identity."],
    "recommended_action": "Confirm identity.",
    "confidence_score": 0.6,
    "answer": None,
    "grounded_mode": "deterministic-evidence-engine",
}


def _copilot_with_replies(replies):
    copilot = FieldServiceCopilot()
    copilot.api_key = "test-key"
    prompts = []

    def fake_gemini(prompt):
        prompts.append(prompt)
        return replies[min(len(prompts), len(replies)) - 1]

    copilot._ask_gemini = fake_gemini
    return copilot, prompts


@pytest.mark.parametrize(
    "question, intent",
    [
        ("What should I inspect first?", "next"),
        ("Why is the flow dropping?", "cause"),
        ("Is it safe to open the casing?", "safety"),
        ("When was it last serviced?", "history"),
        ("Tell me about this pump", "status"),
        (None, "status"),
    ],
)
def test_question_is_routed_to_an_intent(question, intent):
    assert classify_intent(question) == intent


def test_gemini_retries_once_after_an_unknown_citation():
    bad = {"answer": "x", "cited_ids": ["FAKE-1"]}
    good = {"answer": "Check the hydraulic path [EVT-00001]", "cited_ids": ["EVT-00001"]}
    copilot, prompts = _copilot_with_replies([bad, good])
    result = dict(RESULT)
    copilot._apply_llm(result, "why?")
    assert len(prompts) == 2
    assert "FAKE-1" in prompts[1]
    assert result["answer"].startswith("Check the hydraulic path")
    assert "citations verified" in result["grounded_mode"]


def test_gemini_answer_is_dropped_after_two_bad_replies():
    bad = {"answer": "x", "cited_ids": ["FAKE-1"]}
    copilot, prompts = _copilot_with_replies([bad])
    result = dict(RESULT)
    copilot._apply_llm(result, "why?")
    assert len(prompts) == 2
    assert result["answer"] is None
    assert result["grounded_mode"] == "deterministic-evidence-engine"


def test_narration_keeps_only_lines_about_the_right_asset():
    reply = {"lines": {"A-1": "P-005 is fouling, inspect the hydraulic path.", "A-2": "Looks fine.", "A-9": "CV-9 unknown asset."}}
    copilot, prompts = _copilot_with_replies([reply])
    assets = [{"asset_id": "A-1", "tag": "P-005"}, {"asset_id": "A-2", "tag": "CV-002"}]
    assert copilot.narrate(assets) == {"A-1": "P-005 is fouling, inspect the hydraulic path."}
    copilot.narrate(assets)
    assert len(prompts) == 2  # A-2 is asked again, A-1 is cached


def test_narration_is_empty_without_a_key():
    copilot = FieldServiceCopilot()
    copilot.api_key = None
    assert copilot.narrate([{"asset_id": "A-1", "tag": "P-005"}]) == {}
