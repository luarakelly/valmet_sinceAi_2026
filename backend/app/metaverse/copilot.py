"""Evidence-grounded field-service copilot.

Two layers, so the demo never depends on network access:
1. Evidence engine (always runs): telemetry drift vs the asset's own baseline, matching alarms,
   similar historical service cases, knowledge docs and data-quality penalties. Every finding
   carries a source ID from the builder pack.
2. LLM narrative (only when GEMINI_API_KEY is set): Gemini rewrites the evidence into an answer
   to the technician's question. Its output is accepted only if every cited ID exists in the
   evidence set; otherwise the deterministic answer is kept (no hallucinated sources).

Observation vs hypothesis and confidence follow DOC-RAG-GUIDE; boundaries follow DOC-FIELD-SAFETY.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("ask_your_factory.copilot")

DETERMINISTIC_MODE = "deterministic-evidence-engine"
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
FALLBACK_GEMINI_MODELS = ["gemini-3.5-flash", "gemini-3.8-flash"]
MAX_LLM_ATTEMPTS = 2  # first try plus one retry that names the rejected IDs
MAX_NARRATION_WORDS = 24

STATUS_INTENT = "status"
# First matching intent wins, so the order is the priority.
INTENT_KEYWORDS = {
    "safety": {"safe", "safety", "lockout", "loto", "ppe", "permit", "danger", "hazard", "isolate", "isolation"},
    "history": {"history", "before", "last", "previous", "maintenance", "serviced", "service", "repaired"},
    "cause": {"why", "cause", "reason", "trend", "drift", "drifting", "telemetry", "flow", "vibration", "temperature", "pressure", "current", "signal", "dropping"},
    "next": {"next", "inspect", "check", "first", "fix", "repair", "step", "steps", "do", "how", "should"},
}

SIGNALS = {
    "process_pressure_bar": ("Process pressure", "bar"),
    "process_flow_pct": ("Process flow", "%"),
    "position_actual_pct": ("Valve position", "%"),
    "pneumatic_supply_bar": ("Pneumatic supply", "bar"),
    "stiction_index": ("Stiction index", ""),
    "load_for_opening_pct": ("Load for opening", "%"),
    "vibration_mm_s": ("Vibration", "mm/s"),
    "bearing_temp_c": ("Bearing temperature", "°C"),
    "motor_current_a": ("Motor current", "A"),
    "speed_rpm": ("Speed", "rpm"),
    "signal_quality_pct": ("Signal quality", "%"),
    "sensor_bias": ("Sensor bias", ""),
}
DRIFT_T_SCORE = 3.0  # mean shift in standard errors; robust to large diurnal swings
RECENT_FRACTION = 1 / 3
MIN_BASELINE = 12
DQ_PENALTY = {"high": 0.08, "medium": 0.03, "low": 0.01}
MAX_DQ_PENALTY = 0.25
MIN_CONFIDENCE = 0.3


def detect_drift(telemetry: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Signals whose recent mean shifted from the asset's own earlier baseline, strongest first.

    Score = mean difference / standard error (Welch t), so a small but sustained shift in a noisy
    signal (e.g. fouling: flow −9 %, current +4 %) is flagged while random swings are not.
    """
    if len(telemetry) < MIN_BASELINE:
        return []
    ordered = sorted(telemetry, key=lambda r: str(r.get("timestamp")))
    split = int(len(ordered) * (1 - RECENT_FRACTION))
    baseline, recent = ordered[:split], ordered[split:]

    drifts = []
    for key, (name, unit) in SIGNALS.items():
        base = np.array([r[key] for r in baseline if r.get(key) is not None], dtype=float)
        now = np.array([r[key] for r in recent if r.get(key) is not None], dtype=float)
        if len(base) < MIN_BASELINE or len(now) == 0:
            continue
        standard_error = max(float(np.sqrt(base.var() / len(base) + now.var() / len(now))), 1e-6)
        score = (float(now.mean()) - float(base.mean())) / standard_error
        if abs(score) < DRIFT_T_SCORE:
            continue
        drifts.append({
            "signal": key,
            "name": name,
            "unit": unit,
            "baseline": round(float(base.mean()), 2),
            "recent": round(float(now.mean()), 2),
            "change_pct": round(100 * (float(now.mean()) - float(base.mean())) / max(abs(float(base.mean())), 1e-6), 1),
            "t_score": round(score, 1),
            "window": f"{recent[0].get('timestamp')} → {recent[-1].get('timestamp')}",
        })
    return sorted(drifts, key=lambda d: -abs(d["t_score"]))


def classify_intent(question: Optional[str]) -> str:
    """What the technician is asking about; STATUS_INTENT when nothing specific is recognised."""
    words = set(re.findall(r"[a-z]+", (question or "").lower()))
    for intent, keywords in INTENT_KEYWORDS.items():
        if words & keywords:
            return intent
    return STATUS_INTENT


def _cited(citation: Dict[str, Any]) -> str:
    text = citation["description"]
    if f"[{citation['source_id']}]" in text:
        return text
    return f"{text} [{citation['source_id']}]"


def _of_type(result: Dict[str, Any], source_type: str) -> List[Dict[str, Any]]:
    return [c for c in result["citations"] if c["source_type"] == source_type]


def _cause_answer(result: Dict[str, Any]) -> str:
    telemetry = _of_type(result, "telemetry")
    if telemetry:
        observed = "Observation: " + " ".join(_cited(c) for c in telemetry[:2])
    else:
        observed = "Observation: no telemetry signal has drifted from its own baseline."
    events = _of_type(result, "event")[:1]
    cases = _of_type(result, "service_case")[:1]
    context = " ".join(_cited(c) for c in events + cases)
    hypothesis = result["diagnosis_summary"].split(". ")[0].rstrip(".")
    return f"{observed} {hypothesis}. {context}".strip()


def _history_answer(result: Dict[str, Any]) -> str:
    orders = _of_type(result, "work_order")
    events = _of_type(result, "event")
    last_service = "No completed work order on record."
    if orders:
        last_service = "Last service: " + _cited(orders[0])
    return f"{last_service} Recent events: " + " ".join(_cited(c) for c in events[:3])


def _answer_for_intent(intent: str, result: Dict[str, Any]) -> Optional[str]:
    """Deterministic answer to the technician's question, or None to show the general diagnosis."""
    if intent == "cause":
        return _cause_answer(result)
    if intent == "history":
        return _history_answer(result)
    if intent == "safety":
        return " ".join(result["safety_checks"])
    if intent == "next":
        steps = [f"{number}. {action}" for number, action in enumerate(result["recommended_actions"][:3], start=1)]
        return " ".join(steps) + " Safety: " + result["safety_checks"][-1]
    return None


class FieldServiceCopilot:
    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self._last_active_model = self.model
        self._client = None
        self._narrations: Dict[str, str] = {}

    def diagnose_asset(
        self,
        asset: Dict[str, Any],
        state: Dict[str, Any],
        telemetry: List[Dict[str, Any]],
        events: List[Dict[str, Any]],
        work_orders: List[Dict[str, Any]],
        docs: List[Dict[str, Any]],
        cases: List[Dict[str, Any]],
        dq_issues: List[Dict[str, Any]],
        mapping_confidence: Optional[float] = None,
        question: Optional[str] = None,
        flow_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        tag = asset.get("tag", "UNKNOWN")
        issue_code = state.get("issue_code", "NORMAL")
        citations: List[Dict[str, Any]] = []
        evidence: List[str] = []

        def cite(source_type: str, source_id: str, description: str, confidence: float) -> None:
            citations.append({"source_type": source_type, "source_id": source_id, "description": description, "confidence": confidence})

        for drift in detect_drift(telemetry)[:4]:
            source_id = f"TEL-{tag}-{drift['signal']}"
            text = (
                f"{drift['name']} {drift['change_pct']:+}% vs own baseline: {drift['baseline']} → {drift['recent']} {drift['unit']}"
                f" (t = {drift['t_score']}, window {drift['window']}) [{source_id}]"
            )
            evidence.append(text)
            cite("telemetry", source_id, text, 0.9)

        newest_first = sorted(events, key=lambda e: str(e.get("timestamp")), reverse=True)
        relevant_events = sorted(newest_first, key=lambda e: (e.get("event_code") != issue_code, e.get("severity") != "high"))[:3]
        for event in relevant_events:
            text = f"{event['event_type']} {event['event_code']} ({event['severity']}, {event['timestamp']}): {event['description']}"
            evidence.append(f"{text} [{event['event_id']}]")
            cite("event", event["event_id"], text, 0.85)

        matching_cases = [c for c in cases if c.get("historical_issue_code") == issue_code] or cases[:1]
        for case in matching_cases[:2]:
            text = f"{case['historical_interpretation']} → next check: {case['recommended_next_check']}"
            evidence.append(f"Similar case: {text} [{case['case_id']}]")
            cite("service_case", case["case_id"], text, 0.8)

        completed = [w for w in work_orders if w.get("result") != "draft_created"]
        if completed:
            last = completed[0]
            text = f"{last['action']} ({last['maintenance_type']}) → {last['result']}, {last['opened_at']}"
            evidence.append(f"Last work order: {text} [{last['work_order_id']}]")
            cite("work_order", last["work_order_id"], text, 0.8)

        for doc in docs:
            cite("doc", doc["doc_id"], f"{doc['title']}: {doc['content']}", 1.0)

        for issue in dq_issues:
            cite("data_quality", issue["issue_id"], f"{issue['issue_type']} in {issue['source_sheet']} ({issue['severity']})", 1.0)

        confidence = self._confidence(state, dq_issues, mapping_confidence)
        recommended = self._recommended_actions(tag, state, matching_cases)
        safety = self._safety_checks(docs, mapping_confidence)

        if flow_context is not None:
            loop_id = flow_context.get("loop_id", "LOOP-MAIN")
            loop_name = flow_context.get("loop_name", "Process Circuit")
            loop_status = flow_context.get("loop_status", "NORMAL")
            flow_pct = flow_context.get("flow_rate_pct", 100.0)
            topo_text = f"Process circuit: {loop_name} (Status: {loop_status}, flow rate: {flow_pct}%)"
            evidence.append(f"{topo_text} [{loop_id}]")
            cite("process_topology", loop_id, topo_text, 0.95)

            loto = flow_context.get("safety_loto")
            if loto is not None:
                instructions = loto.get("isolation_instructions")
                if instructions:
                    safety.append(f"LOTO Safety: {instructions}")

        diagnosis = self._diagnosis(asset, state, evidence, dq_issues, confidence)

        result = {
            "asset_id": asset.get("asset_id"),
            "tag": tag,
            "asset_class": asset.get("asset_class"),
            "condition_state": state.get("condition_state", "unknown"),
            "health_score": state.get("health_score", 0),
            "issue_code": issue_code,
            "diagnosis": diagnosis,
            "diagnosis_summary": diagnosis,
            "answer": None,
            "multivariate_evidence": evidence,
            "citations": citations,
            "evidence_citations": [c["source_id"] for c in citations],
            "recommended_action": recommended[0],
            "recommended_actions": recommended,
            "safety_guardrails": safety,
            "safety_checks": safety,
            "confidence_score": confidence,
            "model_confidence": confidence,
            "work_order_draft_ready": state.get("condition_state") in ("watch", "degraded", "attention_required"),
            "grounded_mode": DETERMINISTIC_MODE,
            "flow_topology": flow_context,
        }
        result["answer"] = _answer_for_intent(classify_intent(question), result)
        if self.api_key:
            self._apply_llm(result, question)
        return result

    @staticmethod
    def _confidence(state: Dict[str, Any], dq_issues: List[Dict[str, Any]], mapping_confidence: Optional[float]) -> float:
        """Model confidence, reduced by data-quality issues and by an uncertain 3D identity (Q-06)."""
        penalty = min(MAX_DQ_PENALTY, sum(DQ_PENALTY.get(q.get("severity"), 0.0) for q in dq_issues))
        confidence = float(state.get("model_confidence", 0.8)) - penalty
        if mapping_confidence is not None:
            confidence *= 0.5 + 0.5 * mapping_confidence
        return round(max(MIN_CONFIDENCE, confidence), 2)

    @staticmethod
    def _diagnosis(asset: Dict[str, Any], state: Dict[str, Any], evidence: List[str], dq_issues: List[Dict[str, Any]], confidence: float) -> str:
        tag = asset.get("tag")
        if state.get("condition_state") == "healthy":
            return f"{tag} shows no significant deviation (health {state.get('health_score')}/100). Continue routine monitoring."
        observation = f"{len(evidence)} pieces of supporting evidence" if evidence else "no supporting telemetry drift"
        sentences = [
            f"Hypothesis: {state.get('issue_summary', state.get('issue_code'))} on {tag} ({asset.get('asset_class')}).",
            f"Observation: health {state.get('health_score')}/100, state {state.get('condition_state')}, urgency {state.get('urgency')}, with {observation}.",
        ]
        if dq_issues:
            sentences.append(f"{len(dq_issues)} data-quality issues lower confidence to {confidence}; verify locally before acting.")
        return " ".join(sentences)

    @staticmethod
    def _recommended_actions(tag: str, state: Dict[str, Any], cases: List[Dict[str, Any]]) -> List[str]:
        actions = [f"Confirm identity of {tag} on site (QR/NFC tag) before any work."]
        next_check = state.get("recommended_next_check")
        if next_check and next_check != "monitor":
            actions.append(f"Verify: {next_check} ({state.get('knowledge_doc_id')}).")
        for case in cases[:1]:
            actions.append(f"Compare with {case['case_id']}: {case['recommended_next_check']}.")
            actions.append(case["safe_evidence_workflow"])
        if len(actions) == 1:
            actions.append("Continue routine monitoring; no field action needed.")
        return actions

    @staticmethod
    def _safety_checks(docs: List[Dict[str, Any]], mapping_confidence: Optional[float]) -> List[str]:
        checks = [d["content"] + f" [{d['doc_id']}]" for d in docs if d["doc_id"] == "DOC-FIELD-SAFETY"]
        checks.append("Apply site lockout/tagout and permits before opening casings, flanges or wiring.")
        if mapping_confidence is not None and mapping_confidence < 0.7:
            checks.append(f"3D identity confidence is {mapping_confidence}: confirm the physical tag before touching equipment [DOC-3D-MAPPING].")
        return checks

    def _apply_llm(self, result: Dict[str, Any], question: Optional[str]) -> None:
        """Replace narrative fields with a Gemini answer, but only if it cites known sources only."""
        allowed = set(result["evidence_citations"])
        prompt = (
            "You are a field-service copilot talking to a technician standing at the equipment. Use ONLY the evidence JSON below. "
            "Answer the question directly in at most 120 words. Separate observation from hypothesis, state confidence, "
            "cite source IDs in square brackets, and never recommend autonomous physical action (DOC-FIELD-SAFETY).\n"
            f"Technician question: {question or 'Diagnose the current condition and the next safe check.'}\n"
            "Return JSON: {\"answer\": str, \"recommended_actions\": [str], \"cited_ids\": [str]}.\n"
            f"Allowed source IDs: {sorted(allowed)}\n"
            f"Evidence: {json.dumps({k: result[k] for k in ('tag', 'asset_class', 'condition_state', 'health_score', 'issue_code', 'diagnosis', 'citations', 'recommended_actions', 'confidence_score')}, default=str)}"
        )
        for _ in range(MAX_LLM_ATTEMPTS):
            payload = self._ask_gemini(prompt)
            if payload is None:
                return
            problem = self._citation_problem(payload, allowed)
            if problem is None:
                self._accept_llm(result, payload, getattr(self, "_last_active_model", self.model))
                return
            logger.warning("Gemini answer rejected: %s", problem)
            prompt += f"\nYour previous answer was rejected: {problem}. Cite only allowed source IDs."

    @staticmethod
    def _citation_problem(payload: Dict[str, Any], allowed: set) -> Optional[str]:
        answer = payload.get("answer")
        cited = payload.get("cited_ids")
        if not isinstance(answer, str) or not answer.strip():
            return "no answer text"
        if not isinstance(cited, list) or not cited:
            return "no cited_ids"
        unknown = set(cited) - allowed
        if unknown:
            return f"unknown source IDs {sorted(unknown)}"
        return None

    def _accept_llm(self, result: Dict[str, Any], payload: Dict[str, Any], model_used: Optional[str] = None) -> None:
        result["answer"] = payload["answer"]
        actions = payload.get("recommended_actions")
        if isinstance(actions, list) and actions:
            result["recommended_actions"] = [str(action) for action in actions]
            result["recommended_action"] = result["recommended_actions"][0]
        active_model = model_used or self.model
        result["grounded_mode"] = f"{active_model} (citations verified)"

    def _ask_gemini(self, prompt: str) -> Optional[tuple[Dict[str, Any], str] | Dict[str, Any]]:
        """One JSON-mode Gemini call with fallback models; None on total failure."""
        models_to_try = [self.model]
        for m in FALLBACK_GEMINI_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        for model_name in models_to_try:
            try:
                response = self._gemini().models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"response_mime_type": "application/json", "temperature": 0.2},
                )
                payload = json.loads(response.text)
                if isinstance(payload, dict):
                    self._last_active_model = model_name
                    return payload
                logger.warning("Gemini model %s returned %s instead of JSON dict", model_name, type(payload).__name__)
            except Exception as exc:
                logger.warning("Gemini model %s unavailable: %s", model_name, exc)
                continue
        logger.warning("All Gemini models unavailable, keeping deterministic text")
        return None

    def narrate(self, assets: List[Dict[str, Any]]) -> Dict[str, str]:
        """asset_id → one-sentence briefing for a technician walking past it; {} without Gemini.

        Gemini sees only each asset's pack fields. Lines for unknown IDs, empty lines and lines
        that drop the asset tag are discarded, so every kept sentence is about the right asset.
        """
        if not self.api_key:
            return {}
        missing = [a for a in assets if a["asset_id"] not in self._narrations]
        if missing:
            self._narrations.update(self._narrate_batch(missing))
        return {a["asset_id"]: self._narrations[a["asset_id"]] for a in assets if a["asset_id"] in self._narrations}

    def _narrate_batch(self, assets: List[Dict[str, Any]]) -> Dict[str, str]:
        prompt = (
            "A technician is walking past each asset below. For every asset write ONE plain sentence "
            f"(at most {MAX_NARRATION_WORDS} words) with its tag, condition and the single most useful thing to know or check. "
            "Use only the fields given; no invented numbers; never advise autonomous physical action.\n"
            "Return JSON: {\"lines\": {\"<asset_id>\": \"<sentence>\"}}.\n"
            f"Assets: {json.dumps(assets, default=str)}"
        )
        payload = self._ask_gemini(prompt)
        lines = (payload or {}).get("lines")
        if not isinstance(lines, dict):
            return {}
        tags = {a["asset_id"]: a["tag"] for a in assets}
        return {
            asset_id: line.strip()
            for asset_id, line in lines.items()
            if asset_id in tags and isinstance(line, str) and tags[asset_id] in line
        }

    def _gemini(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client


_copilot_instance: Optional[FieldServiceCopilot] = None


def get_copilot() -> FieldServiceCopilot:
    global _copilot_instance
    if _copilot_instance is None:
        _copilot_instance = FieldServiceCopilot()
    return _copilot_instance
