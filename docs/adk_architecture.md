# Gujarat TSR — Google ADK 2.x Workflow

This document describes `adk_agent/`, a re-expression of the TSR pipeline as a
**skill-based [Google Agent Development Kit (ADK) 2.x](https://google.github.io/adk-docs/)
workflow** with a built-in **observability layer** and a **ground-truth feedback
loop**. It runs the full pipeline through a **single command**.

It is a *new orchestration layer* that reuses the existing, battle-tested
internals (`tsr_generator/`, `anyror/`). The Streamlit UI, FastAPI server, legacy
CLI and Docker image are untouched.

---

## 1. Why ADK 2.x (the "most updated protocol")

Google's current recommended stack for building agents (mid-2026) is:

| Layer | Protocol | Role here |
| ----- | -------- | --------- |
| Orchestration | **ADK 2.x** (`google-adk` ≥ 2.2.0) | the pipeline framework |
| Workflow runtime | **ADK 2.0 graph `Workflow`** | the `ingest → extract → assemble` graph |
| Global cross-cutting hooks | **ADK Plugins** | the observability layer |
| Tool ↔ model | MCP | (the repo already has `mcp_server/`; complementary) |
| Agent ↔ agent | A2A | not needed for a single in-process pipeline |

ADK 2.0 (released May 2026; this repo targets v2.2.0) introduced a **graph-based
Workflow runtime** — "a graph-based execution engine for composing deterministic
execution flows … with support for routing, fan-out/fan-in, loops, retry, state
management, dynamic nodes, human-in-the-loop, and nested workflows." We use the
graph runtime as the canonical engine, **Plugins** (registered once on the
`Runner`, firing for every agent/model/tool call) for observability, and the ADK
**evaluation** framework's *golden dataset* concept for ground truth.

References:
- ADK docs: <https://google.github.io/adk-docs/>
- ADK 2.0 overview: <https://google.github.io/adk-docs/2.0/>
- Plugins: <https://google.github.io/adk-docs/plugins/>
- Sequential/graph workflows: <https://google.github.io/adk-docs/agents/workflow-agents/sequential-agents/>
- Evaluation & golden datasets: <https://google.github.io/adk-docs/evaluate/>

---

## 2. The skill graph

```
                ┌──────────────────────── ADK App (root_agent = Workflow) ────────────────────────┐
                │                                                                                   │
  survey/PDF ──▶│  START ─▶ ingest ─────▶ extractor (LlmAgent) ─────▶ assemble ─▶ END               │──▶ TSR .docx
                │           (function)     (Gemini, structured)        (function)                    │    + run record
                │                                                                                   │
                └──────────────────── ObservabilityPlugin (before/after model, agent) ─────────────┘
```

Each pipeline step is a **skill**:

| Skill | Kind | Reuses | What it does |
| ----- | ---- | ------ | ------------ |
| `ingest` | function node | `anyror.AnyRoRScraper`, `services.TranslationService`, `pdf_utils.extract_text_from_pdf` | (survey mode) scrape AnyRoR → PDF; extract PDF text |
| `extractor` | **native ADK `LlmAgent`** | `unified_extractor.build_unified_prompt` | one Gemini call → validated `UnifiedExtraction` |
| `assemble` | function node | `process_entry_details`, `generate_findings_table`, `create_tsr_document` | findings cross-reference + DOCX render |

### The extraction agent (design highlights)

- **Reuses the exact tuned prompt.** The instruction is the existing
  `build_unified_prompt` output (JSON spec + entry-type rules + formatting rules +
  certification patterns + few-shot examples). Because that text is full of literal
  `{ }`, it is supplied as a **callable `InstructionProvider`** — ADK does not apply
  `{state_key}` templating to callable instructions.
- **Validated structured output.** `output_schema=UnifiedExtraction` (Pydantic)
  upgrades "please return JSON" into ADK-enforced structured output, written to
  `session.state['extraction']`.
- **Gemini-native.** Per the project decision the workflow targets Gemini through
  ADK's `google-genai` integration (same `GEMINI_MODEL_NAME` as the legacy path).
- **Learned guidelines** distilled from lawyer corrections are injected into the
  prompt just before the document text (see §4).

### Two engines, one set of skills

`run_pipeline(..., engine=...)`:

- **`pipeline`** (default, robust): deterministic steps run in plain Python; the
  extractor `LlmAgent` runs via an ADK `Runner` so the plugin instruments the model
  call. Clear error handling.
- **`graph`**: the whole `ingest → extractor → assemble` graph runs as an ADK 2.0
  `Workflow` (the most up-to-date orchestration primitive). Exposed as
  `adk_agent.graph.root_agent` for `adk run adk_agent` / `adk web`.

Both produce identical run records and DOCX. Run config (output path, subject
survey) and the live run record are carried out-of-band via a `contextvars`
`RunContext`, since graph nodes pass *data* (not config) between each other.

---

## 3. Observability layer

`ObservabilityPlugin` (a `BasePlugin` registered on the `App`) captures, into a
durable `RunRecord` per run:

- `before_agent` / `after_agent` → a `SkillStep` with timing,
- `before_model` → the **fully rendered prompt** (system instruction + contents),
- `after_model` → the **raw response**, **token usage** (`usage_metadata`), finish
  reason.

Persisted under `adk_agent/runs/<run_id>/`:

| File | Contents |
| ---- | -------- |
| `record.json` | the complete machine-readable record (prompts, responses, tokens, skills, outputs) |
| `extraction.json` | just the structured extraction — **the file a lawyer copies and corrects** |
| `source.txt` | the source document text (for replay / promotion into the golden set) |
| `trace.md` | a human-readable trace (collapsible prompt/response, token table) |

This is the raw material for prompt improvement: for any (possibly wrong)
extraction you can see exactly what prompt produced it.

> ADK also emits OpenTelemetry spans for every agent/tool/LLM call since v1.23, so
> the same run can additionally be shipped to Cloud Trace / Langfuse / Arize if
> desired. The `RunRecord` is the domain-specific, lawyer-facing view on top.

---

## 4. Ground-truth feedback loop

The loop that turns a lawyer's fixes into better prompts **and** a regression
metric:

```
run ─▶ runs/<id>/extraction.json
          │  (lawyer opens the DOCX, fixes a copy of extraction.json)
          ▼
     ground_truth.json
          │  python -m adk_agent feedback import --run <id> --truth ground_truth.json
          ▼
   diff(model, truth)  ─────────────┬─────────────────────────────┐
          │                         │                             │
          ▼                         ▼                             ▼
   field-level Corrections   learned prompt guidelines     golden eval case
   (aligned by entry no.)    (prompting_guidelines.jsonl)  (golden.evalset.json)
                                    │                             │
                                    ▼                             ▼
                    injected into the next extraction     python -m adk_agent eval
                    prompt ("LEARNED CORRECTIONS")        scores model vs ground truth
```

- **Diff** (`feedback/diff.py`): aligns chain-of-title entries by `entry_number`,
  compares land-detail fields, and classifies each difference
  (`land_field`, `entry_type`, `entry_description`, `certification`, `entry_field`,
  `missing_entry`, `extra_entry`). Empty / "Not Available" values are treated as
  absent so only real differences are flagged.
- **Guidelines** (`feedback/guidelines_store.py`): each correction becomes a
  generalised rule with a WRONG/RIGHT example, **deduplicated** by
  `(scope, field, kind, entry_type)` so repeated corrections collapse into one rule
  with a `count` (the prompt stays bounded). `skills/extraction.py` injects the
  top‑N digest into the prompt on the next run.
- **Golden set** (`eval/evalset.py`): the corrected run is promoted into an
  ADK-evalset-shaped `golden.evalset.json` (plus the source text), so the fix
  becomes a permanent regression check.
- **Eval** (`eval/run_eval.py`): re-runs the extractor over every golden case and
  scores it against ground truth — `field_accuracy`, `entry_recall`,
  `type_accuracy` — a single number to watch as prompts/guidelines evolve.

The lawyer correction is the **human-in-the-loop** stage; ADK 2.0's Task API
supports HITL natively, but for this workflow an offline structured-JSON correction
is simpler and fits how lawyers already review the DOCX.

---

## 5. Single command

```bash
# PDF → TSR (offline-capable)
python -m adk_agent --pdf record.pdf --out report.docx
python -m adk_agent --pdf record.pdf --dry-run          # no API key, FakeGemini
python -m adk_agent --pdf record.pdf --engine graph     # ADK 2.0 graph runtime

# Live AnyRoR survey → TSR
python -m adk_agent --survey "Kutch/Abdasa/Keshav/150" --out report.docx

# Feedback + evaluation
python -m adk_agent feedback import --run <run_id> --truth ground_truth.json
python -m adk_agent eval
python -m adk_agent runs          # list recent runs
python -m adk_agent guidelines    # show learned guidelines injected into the prompt
```

`--dry-run` (or simply no `GEMINI_API_KEY`) swaps in an offline `FakeGemini`
`BaseLlm`, so the **entire** pipeline — graph wiring, observability, DOCX render,
run records — executes with no network. That is exactly what the test suite uses.

---

## 6. Best practices applied (from the ADK docs)

- **Structured workflow** via the graph `Workflow` (deterministic, inspectable).
- **Validated structured output** via `output_schema` instead of free-form JSON.
- **Global cross-cutting concerns as a Plugin**, not scattered per-agent callbacks.
- **Let exceptions propagate** out of skills so the framework/orchestrator handles
  them (ADK 2.0 migration guidance) — the orchestrator records and persists errors.
- **Reuse, don't fork**: the agent layer wraps existing tested functions; identical
  inputs produce byte-identical DOCX.
- **Evaluation as a first-class citizen**: a golden dataset + a single regression
  metric, fed by real human corrections.

---

## 7. Configuration

Reuses the existing env vars; adds a few `ADK_*` overrides (see `adk_agent/config.py`):

| Var | Default | Purpose |
| --- | ------- | ------- |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | – | Gemini auth (bridged for ADK) |
| `GEMINI_MODEL_NAME` | `gemini-3.1-pro-preview` | extraction model |
| `ADK_RUNS_DIR` | `adk_agent/runs` | run records location |
| `ADK_GUIDELINES_PATH` | `adk_agent/feedback/prompting_guidelines.jsonl` | learned guidelines |
| `ADK_GOLDEN_EVALSET` | `adk_agent/eval/golden.evalset.json` | golden dataset |

---

## 8. Limitations / next steps

- Live scraping needs portal access, a browser, and a CAPTCHA-solving Gemini key at
  runtime; it is not exercised by the dry-run.
- The dry-run `FakeGemini` returns a fixed payload, so dry-run eval numbers reflect
  the fixture, not real accuracy.
- Guideline synthesis is deterministic (template-based); an optional LLM-judge pass
  could produce richer generalisations.
- The graph engine currently models a linear chain; ADK's graph runtime also
  supports branching/loops/HITL nodes that future work could use (e.g. a retry loop
  when `entry_recall` is low, or a HITL approval node before finalising the DOCX).
