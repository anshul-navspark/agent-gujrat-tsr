"""
Durable run records — the raw material for prompt/extraction improvement.

Every pipeline run produces one :class:`RunRecord` capturing:

  * each skill step (name, status, duration, summary),
  * every LLM call (agent, model, the *fully rendered prompt*, the raw response,
    and token usage),
  * the structured extraction the model produced,
  * the final outputs (DOCX path, entry/finding counts) and status.

It is persisted under ``runs/<run_id>/`` as:

  * ``record.json``     — the complete machine-readable record,
  * ``extraction.json`` — just the structured extraction (what a lawyer copies
    and corrects to produce ground truth),
  * ``trace.md``        — a human-readable trace (prompts/responses/tokens),

so prompt engineers can inspect exactly what was sent and returned, and the
feedback loop can diff the model output against the lawyer-corrected truth.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str, limit: int = 2000) -> str:
    if text is None:
        return ""
    return text if len(text) <= limit else text[:limit] + f"\n…[truncated {len(text) - limit} chars]"


@dataclass
class LlmCall:
    """One model invocation captured by the observability plugin."""

    agent_name: str = ""
    model: str = ""
    started_at: str = field(default_factory=_now_iso)
    duration_ms: int = 0
    prompt: str = ""          # fully rendered prompt sent to the model
    response_text: str = ""   # raw model response text
    prompt_tokens: int = 0
    response_tokens: int = 0
    thinking_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = ""
    error: Optional[str] = None


@dataclass
class SkillStep:
    """One deterministic (or agent) skill execution."""

    name: str
    status: str = "success"  # success | error | skipped
    duration_ms: int = 0
    detail: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class RunRecord:
    """The complete record of a single pipeline run."""

    run_id: str
    created_at: str = field(default_factory=_now_iso)
    mode: str = "pdf"            # pdf | survey
    dry_run: bool = False
    model: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    skills: List[SkillStep] = field(default_factory=list)
    llm_calls: List[LlmCall] = field(default_factory=list)
    extraction: Optional[Dict[str, Any]] = None
    output: Dict[str, Any] = field(default_factory=dict)
    status: str = "running"     # running | success | error
    error: Optional[str] = None

    # ------------------------------------------------------------------ helpers
    def add_skill(self, step: SkillStep) -> SkillStep:
        self.skills.append(step)
        return step

    def add_llm_call(self, call: LlmCall) -> LlmCall:
        self.llm_calls.append(call)
        return call

    @property
    def token_totals(self) -> Dict[str, int]:
        return {
            "prompt_tokens": sum(c.prompt_tokens for c in self.llm_calls),
            "response_tokens": sum(c.response_tokens for c in self.llm_calls),
            "thinking_tokens": sum(c.thinking_tokens for c in self.llm_calls),
            "total_tokens": sum(c.total_tokens for c in self.llm_calls),
        }

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["token_totals"] = self.token_totals
        return d

    # ----------------------------------------------------------------- persist
    def run_dir(self, runs_dir: Path) -> Path:
        return Path(runs_dir) / self.run_id

    def persist(self, runs_dir: Path) -> Path:
        """Write record.json, extraction.json and trace.md; return the run dir."""
        d = self.run_dir(runs_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "record.json").write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if self.extraction is not None:
            (d / "extraction.json").write_text(
                json.dumps(self.extraction, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        (d / "trace.md").write_text(self.to_markdown(), encoding="utf-8")
        return d

    def to_markdown(self) -> str:
        tt = self.token_totals
        lines: List[str] = [
            f"# TSR run `{self.run_id}`",
            "",
            f"- created: {self.created_at}",
            f"- mode: **{self.mode}**  •  dry_run: {self.dry_run}  •  model: `{self.model}`",
            f"- status: **{self.status}**" + (f"  •  error: {self.error}" if self.error else ""),
            f"- inputs: `{json.dumps(self.inputs, ensure_ascii=False)}`",
            f"- tokens: prompt={tt['prompt_tokens']} response={tt['response_tokens']} "
            f"thinking={tt['thinking_tokens']} total={tt['total_tokens']}",
            "",
            "## Skills",
            "",
            "| # | skill | status | ms | detail |",
            "| - | ----- | ------ | -- | ------ |",
        ]
        for i, s in enumerate(self.skills, 1):
            detail = json.dumps(s.detail, ensure_ascii=False)
            detail = detail if len(detail) <= 120 else detail[:117] + "…"
            lines.append(f"| {i} | {s.name} | {s.status} | {s.duration_ms} | {detail} |")

        lines += ["", "## LLM calls", ""]
        for i, c in enumerate(self.llm_calls, 1):
            lines += [
                f"### Call {i} — agent `{c.agent_name}` (model `{c.model}`)",
                "",
                f"- duration: {c.duration_ms} ms  •  finish: {c.finish_reason}",
                f"- tokens: prompt={c.prompt_tokens} response={c.response_tokens} "
                f"thinking={c.thinking_tokens} total={c.total_tokens}",
            ]
            if c.error:
                lines.append(f"- error: {c.error}")
            lines += [
                "",
                "<details><summary>Rendered prompt</summary>",
                "",
                "```",
                _truncate(c.prompt, 6000),
                "```",
                "",
                "</details>",
                "",
                "<details><summary>Raw response</summary>",
                "",
                "```",
                _truncate(c.response_text, 6000),
                "```",
                "",
                "</details>",
                "",
            ]

        if self.output:
            lines += ["## Output", "", "```json", json.dumps(self.output, indent=2, ensure_ascii=False), "```", ""]
        return "\n".join(lines)


class _Timer:
    """Small context manager that records elapsed ms into a target attribute."""

    def __init__(self):
        self._start = 0.0
        self.ms = 0

    def __enter__(self) -> "_Timer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc) -> None:
        self.ms = int((time.monotonic() - self._start) * 1000)
