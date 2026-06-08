# `adk_agent/` — Gujarat TSR on Google ADK 2.x

A skill-based [Google ADK 2.x](https://google.github.io/adk-docs/) workflow that
runs the whole TSR pipeline through one command, with an observability layer and a
ground-truth feedback loop. It **reuses** the existing internals (`tsr_generator/`,
`anyror/`) and leaves the Streamlit/API/CLI/Docker paths untouched.

> Full design: [`docs/adk_architecture.md`](../docs/adk_architecture.md)

## Install

```bash
pip install -r requirements.txt -r requirements-adk.txt   # Python >= 3.11
```

## Run (single command)

```bash
# PDF → TSR. Add --dry-run to run fully offline (no API key) with FakeGemini.
python -m adk_agent --pdf record.pdf --out report.docx
python -m adk_agent --pdf record.pdf --dry-run
python -m adk_agent --pdf record.pdf --engine graph     # ADK 2.0 graph runtime

# Live AnyRoR survey → TSR (needs portal access + GEMINI_API_KEY for the CAPTCHA)
python -m adk_agent --survey "District/Taluka/Village/SurveyNo" --out report.docx
```

Each run writes `adk_agent/runs/<run_id>/` → `record.json`, `extraction.json`,
`source.txt`, `trace.md`, plus the DOCX at `--out`.

## Improve prompts from lawyer corrections

```bash
# 1. A lawyer reviews the DOCX and fixes a copy of runs/<id>/extraction.json
#    (see feedback/ground_truth.example.json for the shape) -> ground_truth.json
# 2. Import the fix: distils prompt guidelines + adds a golden eval case
python -m adk_agent feedback import --run <run_id> --truth ground_truth.json

# 3. See what was learned, and measure the extractor against ground truth
python -m adk_agent guidelines
python -m adk_agent eval
```

## Make it faster / cheaper without losing accuracy

A closed-loop optimizer searches prompt **profiles** (compact or omit the heavy
static prompt blocks, tighten section pruning, route the model, cap thinking /
output) and keeps only the changes that cut tokens/latency **with no accuracy
regression** — measured against lawyer-truth golden cases where available, else
against the current production output (parity).

```bash
python -m adk_agent optimize --dry-run            # offline demo on the bundled sample PDF
python -m adk_agent optimize --corpus ./pdfs      # measure over your own PDFs (live key)
python -m adk_agent optimize --apply              # promote the winning profile to production
python -m adk_agent optimize --show               # inspect the active profile
python -m adk_agent optimize --revert             # back to the untouched 'full' prompt
```

Results land in `adk_agent/optimize/artifacts/` (`report.md`, `leaderboard.jsonl`,
`best_profile.json`). The promoted winner is written to `active_profile.json`,
which every subsequent run reads automatically — fully reversible.

## Layout

```
adk_agent/
  __main__.py        single-command CLI (run | feedback | eval | optimize | runs | guidelines)
  pipeline.py        orchestrator (engine="pipeline" | "graph") + extract_only(_record)
  graph.py           ADK 2.0 Workflow graph + root_agent (for `adk run`/`adk web`)
  app.py             App + Runner + (profile-aware) model resolution
  steps.py           shared pipeline steps (scrape, pdf_text, assemble)
  schemas.py         UnifiedExtraction (Pydantic output schema)
  dry_run_model.py   FakeGemini BaseLlm (offline dry-run / tests)
  skills/            extraction (LlmAgent), pdf_text, scrape, assemble
  observability/     ObservabilityPlugin + RunRecord + RunContext
  feedback/          diff, guidelines store, ground-truth import
  eval/              golden evalset + structured field-accuracy evaluator
  optimize/          prompt profiles, dataset, harness, regression gate, loop
```

## ADK CLI / Dev-UI

The graph is also runnable with native ADK tooling (it exposes `root_agent`):

```bash
adk web .          # from the repo root; pick the "tsr_pipeline" graph
adk run adk_agent
```
