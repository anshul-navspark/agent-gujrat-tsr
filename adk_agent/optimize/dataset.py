"""
Evaluation corpus for the optimizer.

Each :class:`OptCase` is ``(id, pdf_text, mode, reference)``:

  * **golden** — a lawyer-corrected ground-truth extraction (from the golden eval
    set). ``reference`` is the truth; candidates are scored against it (real
    accuracy).
  * **parity** — a land record with no lawyer truth (a corpus PDF or the repo
    sample). ``reference`` is filled later with the *baseline* (current
    production) extraction, so candidates are scored on **drift from current
    production output** — i.e. "did this efficiency change quietly alter what we
    ship?". This needs no ground truth and is the always-available regression
    signal.

Golden cases give the strongest signal; parity cases let the loop run usefully
even before any ground truth exists.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from adk_agent.config import REPO_ROOT, AdkConfig, get_adk_config
from adk_agent.eval.evalset import load_golden_cases

SAMPLE_PDF = REPO_ROOT / "Kutch_Abdasa_Trambo_150_Original.pdf"


@dataclass
class OptCase:
    id: str
    pdf_text: str
    mode: str                          # "golden" | "parity"
    reference: Optional[Dict[str, Any]] = None  # golden truth; None for parity


def _digest(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


def _read_pdf_text(path: Path) -> str:
    # Imported lazily so importing this module never drags in pypdf et al.
    from tsr_generator import extract_text_from_pdf

    return extract_text_from_pdf(str(path)) or ""


def load_cases(
    config: Optional[AdkConfig] = None,
    *,
    corpus_dir: Optional[str] = None,
    include_golden: bool = True,
    include_sample: bool = True,
    limit: Optional[int] = None,
) -> List[OptCase]:
    """Assemble the evaluation corpus (deduplicated by document text)."""
    config = config or get_adk_config()
    cases: List[OptCase] = []
    seen: set = set()

    def _add(case: OptCase) -> None:
        h = _digest(case.pdf_text)
        if not case.pdf_text or h in seen:
            return
        seen.add(h)
        cases.append(case)

    if include_golden:
        for c in load_golden_cases(config):
            truth = c.get("expected_extraction")
            pdf_text = c.get("pdf_text") or ""
            if truth and pdf_text:
                _add(OptCase(id=str(c.get("eval_id")), pdf_text=pdf_text, mode="golden", reference=truth))

    if corpus_dir:
        for pdf in sorted(Path(corpus_dir).glob("*.pdf")):
            _add(OptCase(id=f"corpus:{pdf.stem}", pdf_text=_read_pdf_text(pdf), mode="parity"))

    if include_sample and SAMPLE_PDF.exists():
        _add(OptCase(id=f"sample:{SAMPLE_PDF.stem}", pdf_text=_read_pdf_text(SAMPLE_PDF), mode="parity"))

    if limit:
        cases = cases[:limit]
    return cases
