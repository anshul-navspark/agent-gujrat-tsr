"""
Golden eval set — ground truth captured from lawyer-reviewed runs.

Stored in ADK's ``*.evalset.json`` shape (so it is inspectable with ADK tooling)
with a couple of extra keys (``expected_extraction``, ``pdf_text``, ``survey``)
that drive our structured field-accuracy evaluator.

Each case is keyed by ``eval_id`` (the originating run id, or a caller-supplied
id) so re-importing a corrected run updates the same golden case.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from adk_agent.config import AdkConfig, get_adk_config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_set(eval_set_id: str = "tsr_golden") -> Dict[str, Any]:
    return {
        "eval_set_id": eval_set_id,
        "name": "Gujarat TSR golden dataset",
        "description": "Lawyer-corrected ground-truth extractions used to evaluate the TSR extractor.",
        "eval_cases": [],
    }


def load_evalset(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return _empty_set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("eval_cases", [])
        return data
    except Exception:
        return _empty_set()


def save_evalset(path: Path, data: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_case(
    case_id: str,
    user_text: str,
    truth_extraction: Dict[str, Any],
    pdf_text: str,
    survey: Optional[Dict[str, str]],
    app_name: str,
) -> Dict[str, Any]:
    final_text = json.dumps(truth_extraction, ensure_ascii=False)
    return {
        "eval_id": case_id,
        "conversation": [
            {
                "invocation_id": uuid.uuid4().hex,
                "user_content": {"parts": [{"text": user_text}], "role": "user"},
                "final_response": {"parts": [{"text": final_text}], "role": "model"},
                "intermediate_data": {"tool_uses": [], "intermediate_responses": []},
            }
        ],
        "session_input": {"app_name": app_name, "user_id": "lawyer", "state": {}},
        # --- extra keys for our structured evaluator ---
        "expected_extraction": truth_extraction,
        "pdf_text": pdf_text,
        "survey": survey,
        "created_at": _now(),
    }


def upsert_golden_case(
    config: Optional[AdkConfig],
    case_id: str,
    truth_extraction: Dict[str, Any],
    *,
    pdf_text: str = "",
    survey: Optional[Dict[str, str]] = None,
) -> Path:
    """Add or replace the golden case *case_id*; return the evalset path."""
    config = config or get_adk_config()
    path = config.golden_evalset_path
    data = load_evalset(path)

    user_text = (
        f"Extract the TSR data for survey {survey.get('survey_number')}."
        if survey else "Extract the TSR data from the attached land record."
    )
    case = _build_case(case_id, user_text, truth_extraction, pdf_text, survey, config.app_name)

    cases = [c for c in data["eval_cases"] if c.get("eval_id") != case_id]
    cases.append(case)
    data["eval_cases"] = cases
    save_evalset(path, data)
    return path


def load_golden_cases(config: Optional[AdkConfig] = None) -> List[Dict[str, Any]]:
    config = config or get_adk_config()
    return load_evalset(config.golden_evalset_path).get("eval_cases", [])
