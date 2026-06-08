"""
Loading model extractions and lawyer-corrected ground truth.

The canonical correction format is a structured JSON file with the same shape as
``runs/<run_id>/extraction.json`` (i.e. :class:`UnifiedExtraction`). The intended
human workflow:

    1. Run the pipeline -> ``runs/<run_id>/extraction.json`` is produced.
    2. The lawyer opens the generated DOCX, finds mistakes, and edits a *copy* of
       ``extraction.json`` (fixing types, names, amounts, certification, etc.),
       saving it as e.g. ``ground_truth.json``.
    3. ``python -m adk_agent feedback import --run <run_id> --truth ground_truth.json``.

Both files are validated against :class:`UnifiedExtraction` and returned as the
normalised plain-dict form used everywhere downstream.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

from adk_agent.schemas import UnifiedExtraction


def _load_json(path: Union[str, Path]) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _coerce_extraction(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate/normalise an arbitrary dict into the UnifiedExtraction dict shape."""
    # A run record (record.json) nests the extraction under "extraction".
    if "extraction" in data and "mutation_entries" not in data:
        data = data["extraction"] or {}
    model = UnifiedExtraction.model_validate(data)
    return model.to_legacy_dicts()


def load_extraction(run_dir: Union[str, Path]) -> Dict[str, Any]:
    """Load the model's extraction for a run (from extraction.json or record.json)."""
    run_dir = Path(run_dir)
    extraction_file = run_dir / "extraction.json"
    if extraction_file.exists():
        return _coerce_extraction(_load_json(extraction_file))
    record_file = run_dir / "record.json"
    if record_file.exists():
        return _coerce_extraction(_load_json(record_file))
    raise FileNotFoundError(f"no extraction.json or record.json under {run_dir}")


def load_ground_truth(path: Union[str, Path]) -> Dict[str, Any]:
    """Load and validate a lawyer-corrected ground-truth JSON file."""
    return _coerce_extraction(_load_json(path))
