"""
The no-regression gate.

A candidate profile is **accepted** only if both hold versus the reference
result (the current best):

  * **accuracy holds** — field / entry / type accuracy do not drop by more than a
    tiny tolerance (default: strictly non-decreasing), and
  * **efficiency improves** — average total tokens (or latency) drop by at least
    ``min_token_saving_pct`` percent.

So the loop can only ever trade *equal-or-better accuracy* for *fewer tokens /
lower latency* — never the other way around. This is what "without accuracy
recession" means operationally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from adk_agent.optimize.harness import ProfileResult


def _pct_delta(candidate: float, baseline: float) -> float:
    """Percent change candidate-vs-baseline (negative == improvement for cost metrics)."""
    if baseline <= 0:
        return 0.0
    return (candidate - baseline) / baseline * 100.0


@dataclass
class GateDecision:
    accepted: bool
    accuracy_ok: bool
    efficiency_win: bool
    field_delta: float
    recall_delta: float
    type_delta: float
    token_delta_pct: float
    latency_delta_pct: float
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "accuracy_ok": self.accuracy_ok,
            "efficiency_win": self.efficiency_win,
            "field_delta": round(self.field_delta, 4),
            "recall_delta": round(self.recall_delta, 4),
            "type_delta": round(self.type_delta, 4),
            "token_delta_pct": round(self.token_delta_pct, 2),
            "latency_delta_pct": round(self.latency_delta_pct, 2),
            "reasons": self.reasons,
        }


@dataclass
class RegressionGate:
    field_tol: float = 1e-9
    recall_tol: float = 1e-9
    type_tol: float = 1e-9
    min_token_saving_pct: float = 1.0

    def evaluate(self, baseline: ProfileResult, candidate: ProfileResult) -> GateDecision:
        field_delta = candidate.field_accuracy - baseline.field_accuracy
        recall_delta = candidate.entry_recall - baseline.entry_recall
        type_delta = candidate.type_accuracy - baseline.type_accuracy

        token_delta_pct = _pct_delta(candidate.avg_total_tokens, baseline.avg_total_tokens)
        latency_delta_pct = _pct_delta(candidate.avg_latency_ms, baseline.avg_latency_ms)

        reasons: List[str] = []
        accuracy_ok = (
            field_delta >= -self.field_tol
            and recall_delta >= -self.recall_tol
            and type_delta >= -self.type_tol
        )
        if not accuracy_ok:
            drops = []
            if field_delta < -self.field_tol:
                drops.append(f"field {field_delta:+.4f}")
            if recall_delta < -self.recall_tol:
                drops.append(f"recall {recall_delta:+.4f}")
            if type_delta < -self.type_tol:
                drops.append(f"type {type_delta:+.4f}")
            reasons.append("accuracy regressed: " + ", ".join(drops))

        token_win = token_delta_pct <= -self.min_token_saving_pct
        latency_win = latency_delta_pct <= -self.min_token_saving_pct and token_delta_pct <= 0.0
        efficiency_win = token_win or latency_win
        if not efficiency_win:
            reasons.append(
                f"no efficiency win (tokens {token_delta_pct:+.1f}%, latency {latency_delta_pct:+.1f}%; "
                f"need <= -{self.min_token_saving_pct:.1f}% tokens)"
            )

        accepted = accuracy_ok and efficiency_win
        if accepted:
            reasons.append(f"accepted: tokens {token_delta_pct:+.1f}%, accuracy held")
        return GateDecision(
            accepted=accepted,
            accuracy_ok=accuracy_ok,
            efficiency_win=efficiency_win,
            field_delta=field_delta,
            recall_delta=recall_delta,
            type_delta=type_delta,
            token_delta_pct=token_delta_pct,
            latency_delta_pct=latency_delta_pct,
            reasons=reasons,
        )
