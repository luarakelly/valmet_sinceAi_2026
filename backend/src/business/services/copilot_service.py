"""Evidence-grounded field-service copilot.

Two layers, so the demo never depends on network access:
1. Evidence engine (always runs): telemetry drift vs the asset's own baseline, matching alarms,
   similar historical service cases, knowledge docs and data-quality penalties. Every finding
   carries a source ID from the builder pack.
2. LLM narrative (optional, any `LanguageModel` adapter: Gemini or Claude): the model rewrites the
   evidence into an answer to the technician's question. Its output is accepted only if every
   cited ID exists in the evidence set; otherwise the deterministic answer is kept.

Observation vs hypothesis and confidence follow DOC-RAG-GUIDE; boundaries follow DOC-FIELD-SAFETY.
"""

import json
import logging
from statistics import fmean, pvariance
from typing import Any, Dict, List, Optional

from business.errors import NotFoundError
from business.interfaces.ports.outbound import AssetRepository, LanguageModel, SceneEngine

logger = logging.getLogger("ask_your_factory.copilot")

DETERMINISTIC_MODE = "deterministic-evidence-engine"
GUIDANCE_DOCS = ("DOC-FIELD-SAFETY", "DOC-RAG-GUIDE", "DOC-3D-MAPPING")
TELEMETRY_WINDOW = 144  # 3 days at 30-minute resolution

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
        base = [float(r[key]) for r in baseline if r.get(key) is not None]
        now = [float(r[key]) for r in recent if r.get(key) is not None]
        if len(base) < MIN_BASELINE or len(now) == 0:
            continue
        base_mean, now_mean = fmean(base), fmean(now)
        standard_error = max((pvariance(base) / len(base) + pvariance(now) / len(now)) ** 0.5, 1e-6)
        score = (now_mean - base_mean) / standard_error
        if abs(score) < DRIFT_T_SCORE:
            continue
        drifts.append({
            "signal": key,
            "name": name,
            "unit": unit,
            "baseline": round(base_mean, 2),
            "recent": round(now_mean, 2),
            "change_pct": round(100 * (now_mean - base_mean) / max(abs(base_mean), 1e-6), 1),
            "t_score": round(score, 1),
            "window": f"{recent[0].get('timestamp')} → {recent[-1].get('timestamp')}",
        })
    return sorted(drifts, key=lambda d: -abs(d["t_score"]))


NAVIGATE_KEYWORDS = ("move", "drive", "walk", "navigate", "route", "go", "reach", "travel", "bring me", "take me")
SELECT_KEYWORDS = ("select", "show", "highlight", "look", "focus", "find", "locate", "where")
RESET_KEYWORDS = ("reset", "restart", "home", "origin", "entrance", "entry")


def _detect_action(question: Optional[str]) -> str:
    if not question:
        return "diagnose"
    lower = question.lower()
    for keyword in RESET_KEYWORDS:
        if keyword in lower:
            return "reset"
    for keyword in NAVIGATE_KEYWORDS:
        if keyword in lower:
            return "navigate"
    for keyword in SELECT_KEYWORDS:
        if keyword in lower:
            return "select"
    return "diagnose"


class CopilotService:
    """Use case: evidence-grounded diagnosis for one asset, optionally narrated by an LLM."""

    def __init__(self, assets: AssetRepository, scene: SceneEngine, language_model: Optional[LanguageModel] = None) -> None:
        self._assets = assets
        self._scene = scene
        self._llm = language_model

    def _resolve_target_asset(self, identifier: Optional[str], question: Optional[str]) -> Dict[str, Any]:
        if identifier and identifier.strip():
            found = self._assets.find(identifier.strip())
            if found is None:
                raise NotFoundError(f"Asset with identifier '{identifier}' not found in asset registry.")
            return found

        all_assets = self._assets.list()
        states = self._assets.states()
        if question:
            lower = question.lower()
            for asset in all_assets:
                tag_match = asset["tag"].lower() in lower
                id_match = asset["asset_id"].lower() in lower
                if tag_match or id_match:
                    return asset
            for asset in all_assets:
                class_name = asset["asset_class"].lower().replace("_", " ")
                if class_name in lower:
                    return asset

        faulty_assets = []
        for asset in all_assets:
            state = states.get(asset["asset_id"])
            if state and state.get("condition_state") != "healthy":
                faulty_assets.append((state.get("health_score", 100), asset))
        if faulty_assets:
            faulty_assets.sort(key=lambda item: item[0])
            return faulty_assets[0][1]

        target_id = getattr(self._scene, "target_asset_id", None)
        if target_id:
            found = self._assets.find(target_id)
            if found is not None:
                return found

        if all_assets:
            return all_assets[0]

        raise NotFoundError("No assets available in repository.")

    def diagnose(self, identifier: Optional[str] = None, question: Optional[str] = None) -> Dict[str, Any]:
        """Collect the evidence for an asset and run the evidence engine (+ optional LLM)."""
        asset = self._resolve_target_asset(identifier, question)
        state = self._assets.states([asset["asset_id"]]).get(asset["asset_id"])
        if state is None:
            raise NotFoundError(f"No current state for {asset['asset_id']}.")
        frame = self._scene.find_frame(asset["asset_id"])
        mapping_confidence = None
        if frame is not None:
            mapping_confidence = frame.get("mapping_confidence")

        result = self.diagnose_asset(
            asset=asset,
            state=state,
            telemetry=self._assets.recent_telemetry(asset["asset_id"], TELEMETRY_WINDOW),
            events=self._assets.events(asset["asset_id"], 50),
            work_orders=self._assets.work_orders(asset["asset_id"], 20),
            docs=self._assets.documents([state.get("knowledge_doc_id"), *GUIDANCE_DOCS]),
            cases=self._assets.service_cases(asset["asset_class"]),
            dq_issues=self._assets.data_quality(asset["asset_id"]),
            mapping_confidence=mapping_confidence,
            question=question,
        )
        action = _detect_action(question)
        result["action"] = action
        result["target_asset_id"] = asset["asset_id"]
        return result

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
        }
        if self._llm is not None and self._llm.is_available:
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
        """Replace narrative fields with the LLM answer, but only if it cites known sources only."""
        allowed = set(result["evidence_citations"])
        prompt = (
            "You are an autonomous AI field-service copilot for an industrial plant controlling an inspection robot. "
            "Use ONLY the evidence JSON below. Separate observation from hypothesis, state confidence, cite source IDs in square brackets, "
            "and never recommend autonomous physical repair (DOC-FIELD-SAFETY).\n"
            f"Technician command or question: {question or 'Diagnose the current condition and the next safe check.'}\n"
            "Return JSON: {\"action\": \"navigate\" | \"select\" | \"diagnose\" | \"reset\", \"answer\": str, \"recommended_actions\": [str], \"cited_ids\": [str]}.\n"
            f"Allowed source IDs: {sorted(allowed)}\n"
            f"Evidence: {json.dumps({k: result[k] for k in ('tag', 'asset_class', 'condition_state', 'health_score', 'issue_code', 'diagnosis', 'citations', 'recommended_actions', 'confidence_score')}, default=str)}"
        )
        max_attempts = 2
        for attempt in range(max_attempts):
            payload = self._llm.complete_json(prompt)
            if not payload:
                logger.warning("LLM unavailable, keeping deterministic answer")
                return
            cited = set(payload.get("cited_ids") or [])
            unknown = cited - allowed
            if unknown:
                logger.warning("LLM cited unknown sources %s; retrying", unknown)
                prompt += f"\nYour previous answer was rejected: unknown source IDs {sorted(unknown)}. Cite ONLY allowed source IDs: {sorted(allowed)}."
                continue
            answer = payload.get("answer")
            if not answer:
                return
            result["answer"] = answer
            actions = payload.get("recommended_actions")
            if actions:
                result["recommended_actions"] = actions
                result["recommended_action"] = actions[0]
            action = payload.get("action")
            if action in ("navigate", "select", "diagnose", "reset"):
                result["action"] = action
            result["grounded_mode"] = f"{self._llm.name} (citations verified)"
            return
