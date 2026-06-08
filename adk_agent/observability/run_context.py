"""
Run context — the carrier that threads immutable run config + the live
:class:`RunRecord` through the ADK graph.

ADK 2.0 graph nodes pass *data* positionally between nodes, but the pipeline
also needs *config* (where to write the DOCX, the subject survey, options) and a
shared place to collect step/LLM records.  We carry that out-of-band via a
``contextvars.ContextVar`` (plus a plain module-global fallback) so that:

  * deterministic skill nodes (`ingest`, `assemble`) can read run config and
    append :class:`SkillStep` records, and
  * the observability :class:`ObservabilityPlugin` (which only receives ADK's own
    callback contexts) can append :class:`LlmCall` records to the *same* record.

A run context is established for the duration of one pipeline invocation.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from adk_agent.observability.run_record import RunRecord


@dataclass
class RunContext:
    """Everything a single pipeline run needs, shared across graph nodes."""

    record: RunRecord
    # Immutable run configuration (not threaded through node I/O).
    output_path: str = ""
    pdf_path: Optional[str] = None
    pdf_text: str = ""
    options: Dict[str, Any] = field(default_factory=dict)
    runs_dir: Optional[Path] = None
    # Learned prompt guidelines injected into the extraction prompt this run.
    guidelines_text: str = ""


_current: "contextvars.ContextVar[Optional[RunContext]]" = contextvars.ContextVar(
    "adk_tsr_run_context", default=None
)
# Belt-and-suspenders fallback in case a callback runs in a context that did not
# inherit the ContextVar (e.g. a thread spun up deep inside a dependency).
_current_global: Optional[RunContext] = None


def new_run_context(record: RunRecord, **kwargs) -> RunContext:
    return RunContext(record=record, **kwargs)


def set_current_run(ctx: Optional[RunContext]) -> None:
    global _current_global
    _current.set(ctx)
    _current_global = ctx


def current_run() -> Optional[RunContext]:
    return _current.get() or _current_global
