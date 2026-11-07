"""What the detector looks for: prompt text, scene label and the pack asset class it stands for."""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Term:
    prompt: str
    label: str
    asset_class: Optional[str]


# Order matters little; every term is a separate prompt phrase. Asset classes are the 5 in Asset_Master.
VOCABULARY: Tuple[Term, ...] = (
    Term("crate", "CRATE", None),
    Term("pallet", "PALLET", None),
    Term("pipe", "PIPE", None),
    Term("valve", "VALVE", "CONTROL_VALVE"),
    Term("handwheel", "HANDWHEEL", "CONTROL_VALVE"),
    Term("pump", "PUMP", "PROCESS_PUMP"),
    Term("electric motor", "ELECTRIC_MOTOR", "ELECTRIC_MOTOR"),
    Term("pressure gauge", "PRESSURE_GAUGE", "PRESSURE_TRANSMITTER"),
    Term("vibration sensor", "VIBRATION_SENSOR", "VIBRATION_SENSOR"),
    Term("fire extinguisher", "FIRE_EXTINGUISHER", None),
    Term("electrical cabinet", "ELECTRICAL_CABINET", None),
    Term("tank", "TANK", None),
    Term("hazard sign", "HAZARD_SIGN", None),
)
PROMPT_SEPARATOR = " . "


def prompt_text() -> str:
    """The single caption GroundingDINO expects: phrases separated by ' . ' and a closing dot."""
    return PROMPT_SEPARATOR.join(term.prompt for term in VOCABULARY) + " ."


def term_for_phrase(phrase: str) -> Optional[Term]:
    """Map a detected phrase (possibly a fragment such as 'electric') back to its term."""
    text = phrase.strip().lower()
    for term in VOCABULARY:
        if text == term.prompt:
            return term
    for term in VOCABULARY:
        if text and text in term.prompt.split():
            return term
    return None
