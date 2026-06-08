"""
Diff engine — align a model extraction against lawyer ground truth.

Produces a list of field-level :class:`Correction` records, aligning chain-of-title
entries by ``entry_number`` and comparing land-detail fields head-to-head. Empty /
"Not Available" values are treated as absent so we only flag *real* differences.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

LAND_FIELDS = [
    "village_name", "taluka_name", "district_name", "survey_number",
    "old_survey_number", "total_area", "nature_of_land", "owner",
]
ENTRY_FIELDS = [
    "type", "date", "description", "entry_status",
    "certification_status", "certification_official", "certification_date",
]

_EMPTY = {"", "not available", "n/a", "na", "none", "-"}


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "").strip())


def _is_empty(v: Any) -> bool:
    return _norm(v).lower() in _EMPTY


def _equal(a: Any, b: Any) -> bool:
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return True
    if _is_empty(a) and _is_empty(b):
        return True
    return na.lower() == nb.lower()


def _kind_for(scope: str, fieldname: str) -> str:
    if scope == "land_details":
        return "land_field"
    if fieldname == "type":
        return "entry_type"
    if fieldname == "description":
        return "entry_description"
    if fieldname.startswith("certification") or fieldname == "entry_status":
        return "certification"
    return "entry_field"


@dataclass
class Correction:
    """One field-level difference between model output and ground truth."""

    scope: str                       # "land_details" | "entry"
    field: str                       # field name (or "" for whole-entry add/remove)
    kind: str                        # land_field | entry_type | entry_description | certification | entry_field | missing_entry | extra_entry
    model_value: str = ""
    truth_value: str = ""
    entry_number: Optional[str] = None
    context_type: str = ""           # truth entry type, for context

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _entries_by_number(extraction: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for e in extraction.get("mutation_entries") or []:
        num = _norm(e.get("entry_number"))
        if num:
            out[num] = e
    return out


def diff_extractions(model: Dict[str, Any], truth: Dict[str, Any]) -> List[Correction]:
    """Return the list of corrections that turn *model* into *truth*."""
    corrections: List[Correction] = []

    # --- land details ---
    m_land = model.get("land_details") or {}
    t_land = truth.get("land_details") or {}
    for f in LAND_FIELDS:
        if not _equal(m_land.get(f), t_land.get(f)):
            corrections.append(
                Correction(
                    scope="land_details", field=f, kind="land_field",
                    model_value=_norm(m_land.get(f)), truth_value=_norm(t_land.get(f)),
                )
            )

    # --- entries (aligned by entry_number) ---
    m_entries = _entries_by_number(model)
    t_entries = _entries_by_number(truth)

    for num, t_entry in t_entries.items():
        ctx_type = _norm(t_entry.get("type"))
        if num not in m_entries:
            corrections.append(
                Correction(
                    scope="entry", field="", kind="missing_entry",
                    truth_value=_norm(t_entry.get("description"))[:300],
                    entry_number=num, context_type=ctx_type,
                )
            )
            continue
        m_entry = m_entries[num]
        for f in ENTRY_FIELDS:
            if not _equal(m_entry.get(f), t_entry.get(f)):
                corrections.append(
                    Correction(
                        scope="entry", field=f, kind=_kind_for("entry", f),
                        model_value=_norm(m_entry.get(f)), truth_value=_norm(t_entry.get(f)),
                        entry_number=num, context_type=ctx_type,
                    )
                )

    for num, m_entry in m_entries.items():
        if num not in t_entries:
            corrections.append(
                Correction(
                    scope="entry", field="", kind="extra_entry",
                    model_value=_norm(m_entry.get("description"))[:300],
                    entry_number=num, context_type=_norm(m_entry.get("type")),
                )
            )

    return corrections
