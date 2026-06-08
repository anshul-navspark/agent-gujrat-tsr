"""
Deterministic entity-map grounding — a zero-LLM-cost "tool" pre-pass.

Land records are dense with structured tokens the model routinely fumbles:
survey numbers (often with ``/pN`` subdivisions and ``(khata)`` qualifiers),
dates, and rupee amounts. A large model usually gets these right; a *smaller,
cheaper* model is more likely to drop or mangle one.

Following the entity-grounding / deterministic-preprocessing pattern (cf.
Google's ``langextract`` and ``sourcery``), this module extracts those tokens
**deterministically with regex** and renders a compact "VERIFIED ENTITIES" block
that is injected into the extraction prompt. It costs no LLM tokens to produce,
anchors the model on exact source tokens, and is what lets a flash-class model
hold accuracy on the error-prone multi-survey / khata fields.

Pure functions, no LLM, no network — fully testable offline.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from tsr_generator.extractors.unified_extractor import _identify_entry_numbers_fast
from tsr_generator.utils.text_utils import convert_gujarati_to_english_numerals

# High-precision patterns (English digits, after Gujarati-numeral normalisation).
# We intentionally only capture *structured* survey tokens (a subdivision /pN or a
# parenthetical khata) so the grounding block stays signal, not every stray number.
_SURVEY_SUBDIV_RE = re.compile(r"\b\d{1,4}/p\d{1,3}(?:\(\d{1,4}\))?")
_SURVEY_KHATA_RE = re.compile(r"\b\d{1,4}\(\d{1,4}\)")
_KHATA_RE = re.compile(r"\d{1,4}\((\d{1,4})\)")
_DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
_AMOUNT_RE = re.compile(r"(?:Rs\.?|રૂ\.?|રુ\.?)\s*([\d][\d,]{1,})")


def _sorted_unique(items: List[str]) -> List[str]:
    return sorted(set(i for i in items if i))


def _to_english(tok: str) -> str:
    return convert_gujarati_to_english_numerals(str(tok)).strip()


def build_entity_map(pdf_text: str) -> Dict[str, Any]:
    """Extract structured tokens (surveys, khata, dates, amounts, entries) via regex."""
    text = convert_gujarati_to_english_numerals(pdf_text or "")
    surveys = _sorted_unique(_SURVEY_SUBDIV_RE.findall(text) + _SURVEY_KHATA_RE.findall(text))
    khata = sorted({m for m in _KHATA_RE.findall(text)}, key=lambda x: int(x))
    dates = _sorted_unique(_DATE_RE.findall(text))
    amounts = _sorted_unique(_AMOUNT_RE.findall(text))
    # The fast detector runs on raw text (so it catches Gujarati-digit entries);
    # normalise them to English numerals and order numerically.
    raw_entries = {_to_english(e) for e in _identify_entry_numbers_fast(pdf_text or "")}
    entries = sorted((e for e in raw_entries if e), key=lambda x: int(x) if x.isdigit() else 1 << 30)
    return {
        "survey_numbers": surveys,
        "khata_numbers": khata,
        "dates": dates,
        "amounts": amounts,
        "entry_numbers": entries,
    }


def render_entity_map_block(emap: Dict[str, Any], *, max_items: int = 60) -> str:
    """Render the entity map as a compact grounding block (empty if nothing found)."""
    lines: List[str] = []

    def _row(label: str, values: List[str], cap: int) -> None:
        if values:
            shown = ", ".join(values[:cap])
            more = f" (+{len(values) - cap} more)" if len(values) > cap else ""
            lines.append(f"- {label}: {shown}{more}")

    _row("Survey numbers (with khata in parentheses)", emap.get("survey_numbers", []), max_items)
    _row("Khata numbers", emap.get("khata_numbers", []), max_items)
    _row("Dates", emap.get("dates", []), 40)
    _row("Amounts (Rs.)", emap.get("amounts", []), 30)

    entries = [str(e) for e in emap.get("entry_numbers", [])]
    if not lines and not entries:
        return ""

    out = [
        "VERIFIED ENTITIES (extracted deterministically from the source as grounding "
        "hints — use these exact survey/khata tokens where they apply and never invent "
        "values not present in the document):"
    ]
    out.extend(lines)
    if entries:
        # Entry completeness is the #1 recall driver for a smaller model. Provide the
        # detected numbers as candidates (the detector is heuristic — may miss or
        # over-include), and nudge against the real failure mode: stopping early.
        out.append(
            f"- Candidate entry numbers detected ({len(entries)}): "
            + ", ".join(entries[:max_items])
            + ". Verify each against the Entry Details table and capture EVERY genuine "
            "entry — do not stop early or drop entries; add any real entries this list misses."
        )
    return "\n".join(out) + "\n"


def entity_map_block(pdf_text: str) -> str:
    """Convenience: build + render the grounding block for *pdf_text*."""
    return render_entity_map_block(build_entity_map(pdf_text))
