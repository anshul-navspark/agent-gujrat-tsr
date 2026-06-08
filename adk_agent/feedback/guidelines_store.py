"""
Learned prompt guidelines — the persistent memory of the feedback loop.

Lawyer corrections are distilled into concise, *generalised* guidelines stored as
JSONL (``prompting_guidelines.jsonl``). On the next run, the extraction skill
injects a rendered digest of them into the prompt (see
``skills.extraction.inject_guidelines``), so the model learns from past mistakes.

Guidelines are deduplicated by ``(scope, field, kind, entry_type)`` so repeated
corrections of the same flavour collapse into a single rule with a ``count`` and
a refreshed before/after example — the prompt stays bounded while reflecting the
most common and most recent corrections.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from adk_agent.config import AdkConfig, get_adk_config
from adk_agent.feedback.diff import Correction


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(s: str, n: int) -> str:
    s = (s or "").strip().replace("\n", " ⏎ ")
    return s if len(s) <= n else s[: n - 1] + "…"


@dataclass
class Guideline:
    id: str
    scope: str
    field: str
    kind: str
    entry_type: str
    rule: str
    example_wrong: str = ""
    example_right: str = ""
    count: int = 1
    first_seen: str = field(default_factory=_now)
    last_seen: str = field(default_factory=_now)
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _make_id(scope: str, fieldname: str, kind: str, entry_type: str) -> str:
    raw = f"{scope}|{fieldname}|{kind}|{entry_type}".lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def synthesize_guideline(
    c: Correction,
    model_entry: Optional[Dict[str, Any]] = None,
    truth_entry: Optional[Dict[str, Any]] = None,
    source_run: str = "",
) -> Guideline:
    """Turn a single :class:`Correction` into a generalised :class:`Guideline`."""
    et = c.context_type or ""
    wrong, right = c.model_value, c.truth_value

    if c.kind == "entry_type":
        desc = (truth_entry or {}).get("description", "")
        rule = (
            f"Classify entries that read like the RIGHT example as type '{c.truth_value}' "
            f"(previously misclassified as '{c.model_value}')."
        )
        wrong = f"type={c.model_value}"
        right = f"type={c.truth_value} — {desc}"
    elif c.kind == "entry_description":
        rule = (
            f"For {et or 'these'} entries, phrase the description like the RIGHT example "
            f"(match wording, ordering and which facts are included/omitted)."
        )
    elif c.kind == "certification":
        rule = (
            f"Read the 'Remarks of the Inspecting Officer' column carefully: for {et or 'such'} "
            f"entries the '{c.field}' should be '{c.truth_value}', not '{c.model_value}'."
        )
    elif c.kind == "land_field":
        rule = f"Extract land detail '{c.field}' exactly as recorded (correct value: '{c.truth_value}')."
    elif c.kind == "missing_entry":
        rule = (
            f"Do NOT drop entries: entry {c.entry_number} ({et}) was missing and must be "
            f"included. Render it like the RIGHT example."
        )
        right = c.truth_value
    elif c.kind == "extra_entry":
        rule = (
            f"Entry {c.entry_number} should NOT be a standalone {et} entry in the report "
            f"(it was over-extracted — likely NOT RELATED to the subject survey or spurious)."
        )
        wrong = c.model_value
    else:  # entry_field
        rule = (
            f"For {et or 'these'} entries, field '{c.field}' should be '{c.truth_value}', "
            f"not '{c.model_value}'."
        )

    gid = _make_id(c.scope, c.field, c.kind, et)
    return Guideline(
        id=gid, scope=c.scope, field=c.field, kind=c.kind, entry_type=et,
        rule=rule, example_wrong=_truncate(wrong, 240), example_right=_truncate(right, 280),
        sources=[source_run] if source_run else [],
    )


# --------------------------------------------------------------------- storage
def load_guidelines(path: Path) -> List[Guideline]:
    path = Path(path)
    if not path.exists():
        return []
    out: List[Guideline] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Guideline(**json.loads(line)))
        except Exception:
            continue
    return out


def _save_all(path: Path, guidelines: List[Guideline]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(g.to_dict(), ensure_ascii=False) for g in guidelines) + "\n",
        encoding="utf-8",
    )


def upsert_guidelines(path: Path, new: List[Guideline]) -> List[Guideline]:
    """Merge *new* guidelines into the store (dedupe by id; bump count + refresh example)."""
    existing = {g.id: g for g in load_guidelines(path)}
    for g in new:
        if g.id in existing:
            cur = existing[g.id]
            cur.count += 1
            cur.last_seen = g.last_seen
            cur.rule = g.rule
            if g.example_wrong:
                cur.example_wrong = g.example_wrong
            if g.example_right:
                cur.example_right = g.example_right
            for s in g.sources:
                if s and s not in cur.sources:
                    cur.sources.append(s)
        else:
            existing[g.id] = g
    merged = list(existing.values())
    _save_all(path, merged)
    return merged


# --------------------------------------------------------------------- render
def _sorted_for_prompt(guidelines: List[Guideline]) -> List[Guideline]:
    return sorted(guidelines, key=lambda g: (g.count, g.last_seen), reverse=True)


def render_guidelines_for_prompt(
    config: Optional[AdkConfig] = None, path: Optional[Path] = None, limit: int = 40
) -> str:
    """Render the compact guideline digest injected into the extraction prompt."""
    config = config or get_adk_config()
    path = path or config.guidelines_path
    guidelines = _sorted_for_prompt(load_guidelines(path))[:limit]
    if not guidelines:
        return ""
    lines: List[str] = []
    for g in guidelines:
        tag = g.entry_type or g.scope
        head = f"- [{tag}/{g.field or g.kind}] {g.rule}"
        lines.append(head)
        if g.example_wrong:
            lines.append(f"    WRONG: {g.example_wrong}")
        if g.example_right:
            lines.append(f"    RIGHT: {g.example_right}")
    return "\n".join(lines)


def write_markdown(config: Optional[AdkConfig] = None) -> Path:
    """Render a human-readable guidelines doc next to the JSONL store."""
    config = config or get_adk_config()
    guidelines = _sorted_for_prompt(load_guidelines(config.guidelines_path))
    lines = [
        "# Learned extraction guidelines",
        "",
        "_Auto-generated from lawyer corrections via `python -m adk_agent feedback import`._",
        f"_{len(guidelines)} guideline(s)._",
        "",
    ]
    by_kind: Dict[str, List[Guideline]] = {}
    for g in guidelines:
        by_kind.setdefault(g.kind, []).append(g)
    for kind, items in by_kind.items():
        lines += [f"## {kind} ({len(items)})", ""]
        for g in items:
            tag = g.entry_type or g.scope
            lines.append(f"- **[{tag}/{g.field or g.kind}]** (seen {g.count}×) {g.rule}")
            if g.example_wrong:
                lines.append(f"  - WRONG: `{g.example_wrong}`")
            if g.example_right:
                lines.append(f"  - RIGHT: `{g.example_right}`")
        lines.append("")
    md = "\n".join(lines)
    Path(config.guidelines_md_path).write_text(md, encoding="utf-8")
    return Path(config.guidelines_md_path)
