"""
Evaluation harness — run a profile over the corpus and measure it.

For each case we run *only* the extraction skill (no DOCX, no persistence) under
the candidate profile, then read back from the observability run record:

  * **accuracy** — field / entry / type accuracy vs the case reference
    (``score_extraction`` reuses the feedback diff engine), and
  * **efficiency** — prompt / total / thinking tokens and per-call latency.

The baseline (production ``full`` profile) is run once; its extractions become
the *parity* references, and its metrics are the bar every candidate is gated
against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from adk_agent.config import AdkConfig, get_adk_config
from adk_agent.eval.run_eval import score_extraction
from adk_agent.optimize.dataset import OptCase
from adk_agent.optimize.profiles import PromptProfile, estimate_cost


@dataclass
class CaseScore:
    id: str
    mode: str
    field_accuracy: float = 0.0
    entry_recall: float = 0.0
    type_accuracy: float = 0.0
    prompt_tokens: int = 0
    total_tokens: int = 0
    thinking_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    num_corrections: int = 0
    error: Optional[str] = None


@dataclass
class CaseRun:
    """Raw result of running a profile on one case (pre-scoring)."""

    case: OptCase
    extraction: Optional[Dict[str, Any]] = None
    prompt_tokens: int = 0
    total_tokens: int = 0
    thinking_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    model: str = ""
    error: Optional[str] = None


@dataclass
class ProfileResult:
    profile: PromptProfile
    n_cases: int = 0
    field_accuracy: float = 1.0
    entry_recall: float = 1.0
    type_accuracy: float = 1.0
    avg_prompt_tokens: float = 0.0
    avg_total_tokens: float = 0.0
    avg_thinking_tokens: float = 0.0
    avg_latency_ms: float = 0.0
    avg_cost_usd: float = 0.0
    model: str = ""
    per_case: List[CaseScore] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "profile": self.profile.name,
            "model": self.model,
            "n_cases": self.n_cases,
            "field_accuracy": round(self.field_accuracy, 4),
            "entry_recall": round(self.entry_recall, 4),
            "type_accuracy": round(self.type_accuracy, 4),
            "avg_prompt_tokens": round(self.avg_prompt_tokens, 1),
            "avg_total_tokens": round(self.avg_total_tokens, 1),
            "avg_thinking_tokens": round(self.avg_thinking_tokens, 1),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "avg_cost_usd": round(self.avg_cost_usd, 6),
        }


async def run_profile(
    config: Optional[AdkConfig], profile: PromptProfile, cases: List[OptCase]
) -> List[CaseRun]:
    """Run *profile* over every case; capture extraction + token/latency (no scoring)."""
    from adk_agent.pipeline import extract_only_record  # lazy: avoids import cycle

    config = config or get_adk_config()
    runs: List[CaseRun] = []
    for case in cases:
        try:
            extraction, record = await extract_only_record(
                config, case.pdf_text, profile=profile, use_active_profile=False
            )
            tt = record.token_totals
            latency = sum(c.duration_ms for c in record.llm_calls)
            cost = sum(
                estimate_cost(c.model, c.prompt_tokens, c.response_tokens + c.thinking_tokens)
                for c in record.llm_calls
            )
            model = record.llm_calls[0].model if record.llm_calls else str(profile.model_name or "")
            runs.append(
                CaseRun(
                    case=case,
                    extraction=extraction,
                    prompt_tokens=tt["prompt_tokens"],
                    total_tokens=tt["total_tokens"],
                    thinking_tokens=tt["thinking_tokens"],
                    latency_ms=latency,
                    cost_usd=cost,
                    model=model,
                )
            )
        except Exception as e:  # surface but keep going
            runs.append(CaseRun(case=case, error=str(e)))
    return runs


def build_references(cases: List[OptCase], baseline_runs: List[CaseRun]) -> Dict[str, Dict[str, Any]]:
    """
    Reference extraction per case: golden truth, else the baseline (production)
    extraction (so candidates are gated on drift from current output).
    """
    base_by_id = {r.case.id: r for r in baseline_runs}
    refs: Dict[str, Dict[str, Any]] = {}
    for case in cases:
        if case.mode == "golden" and case.reference is not None:
            refs[case.id] = case.reference
        else:
            br = base_by_id.get(case.id)
            if br and br.extraction is not None:
                refs[case.id] = br.extraction
    return refs


def score_runs(
    profile: PromptProfile, runs: List[CaseRun], references: Dict[str, Dict[str, Any]]
) -> ProfileResult:
    """Score profile *runs* against *references* and aggregate."""
    per_case: List[CaseScore] = []
    for r in runs:
        if r.error or r.extraction is None:
            per_case.append(CaseScore(id=r.case.id, mode=r.case.mode, error=r.error or "no extraction"))
            continue
        ref = references.get(r.case.id)
        if ref is None:
            # No reference available (e.g. parity case whose baseline run failed).
            per_case.append(
                CaseScore(
                    id=r.case.id, mode=r.case.mode,
                    prompt_tokens=r.prompt_tokens, total_tokens=r.total_tokens,
                    thinking_tokens=r.thinking_tokens, latency_ms=r.latency_ms,
                    cost_usd=r.cost_usd, error="no reference",
                )
            )
            continue
        sc = score_extraction(r.extraction, ref)
        per_case.append(
            CaseScore(
                id=r.case.id, mode=r.case.mode,
                field_accuracy=sc["field_accuracy"], entry_recall=sc["entry_recall"],
                type_accuracy=sc["type_accuracy"], num_corrections=sc["num_corrections"],
                prompt_tokens=r.prompt_tokens, total_tokens=r.total_tokens,
                thinking_tokens=r.thinking_tokens, latency_ms=r.latency_ms,
                cost_usd=r.cost_usd,
            )
        )

    scored = [c for c in per_case if c.error is None]
    n = len(scored)

    def mean(attr: str) -> float:
        return sum(getattr(c, attr) for c in scored) / n if n else 0.0

    models = [r.model for r in runs if getattr(r, "model", "")]
    return ProfileResult(
        profile=profile,
        n_cases=n,
        field_accuracy=mean("field_accuracy") if n else 1.0,
        entry_recall=mean("entry_recall") if n else 1.0,
        type_accuracy=mean("type_accuracy") if n else 1.0,
        avg_prompt_tokens=mean("prompt_tokens"),
        avg_total_tokens=mean("total_tokens"),
        avg_thinking_tokens=mean("thinking_tokens"),
        avg_latency_ms=mean("latency_ms"),
        avg_cost_usd=mean("cost_usd"),
        model=(models[0].replace("fake-", "") if models else str(profile.model_name or "")),
        per_case=per_case,
    )


async def evaluate_profile(
    config: Optional[AdkConfig],
    profile: PromptProfile,
    cases: List[OptCase],
    references: Dict[str, Dict[str, Any]],
) -> ProfileResult:
    """Convenience: run *profile* and score it against *references*."""
    runs = await run_profile(config, profile, cases)
    return score_runs(profile, runs, references)
