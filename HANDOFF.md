# Handoff — Efficiency optimizer + legacy cleanup (2026-06-08)

Branch: **`claude/quirky-mendel-d0b8Z`** (PR #7). All work below is committed and
pushed. Offline test suite: **266 passed**.

> Companion docs: design in [`docs/adk_architecture.md`](docs/adk_architecture.md)
> (§5 = the optimizer), usage in [`adk_agent/README.md`](adk_agent/README.md),
> and the real ground-truth audit in
> [`LAWYER_REVIEW_NOTES_2026_05_20.md`](LAWYER_REVIEW_NOTES_2026_05_20.md).

---

## TL;DR

1. **Deprecated dead legacy code** — unified single-call extraction is now the
   only path; removed the `USE_OPTIMIZED_EXTRACTION=false` branch + the unused
   two-pass subsystem (and its tests). Streamlit/API/MCP/CLI still work.
2. **Built a closed-loop efficiency optimizer** (`adk_agent/optimize/`) — a
   bounded **measure → gate → promote** loop that searches prompt/model profiles
   for **cost + latency wins with no accuracy regression**, gated against a
   golden set (lawyer truth) or, absent that, parity-vs-current-production.
3. **Added the cheaper/faster levers you asked for** — `gemini-3.5-flash` model
   routing, a deterministic **entity-map grounding** "tool", and a **cost**
   dimension in the gate.
4. **Validated flash live** (your key, ~5 calls): flash is **~2.5× faster and
   ~25–53% cheaper**, but **regresses accuracy** (drops real entries) — so the
   gate correctly blocks it. The lawyer review independently confirms this.

**Standing recommendation: do NOT promote `gemini-3.5-flash` for the main
extractor yet.** It is built and available as a *gated* lever; promote only after
real golden cases prove it holds accuracy. (See "The flash question", below.)

---

## What changed (3 commits on top of the ADK workflow)

| Commit | Summary |
| --- | --- |
| `8f82a48` | **Deprecate dead legacy code.** Collapse `tsr_generator/__init__.py` to always-optimized; remove the two-pass `extract_all_structured` + `pass1_prompt`/`pass2_prompt`/`template_renderer` (+ their tests) + `compare_extraction_methods`; repoint `python -m tsr_generator` and the MCP `generate_tsr` tool onto the optimized generator (and fix the CLI's pre-existing broken `setup_logging` import / `args.output` bug); mark the original 3-call `tsr_generator/api/tsr_generator.py` deprecated. |
| `a3861bf` | **Closed-loop optimizer** (`adk_agent/optimize/`): profiles, dataset, harness, regression gate, loop + `python -m adk_agent optimize` CLI; FakeGemini now counts the system instruction so token savings are measurable offline. |
| `11118f9` | **Flash routing + entity-map grounding + cost gate**: route to `gemini-3.5-flash`; deterministic `adk_agent/skills/entity_map.py` grounding pre-pass; per-model USD pricing so the gate values the cheaper model, not just token count. |

---

## The optimizer — how it works & how to run it

```bash
python -m adk_agent optimize --dry-run            # offline demo on the bundled sample PDF
python -m adk_agent optimize --corpus ./pdfs      # measure over real PDFs (needs GEMINI_API_KEY)
python -m adk_agent optimize --apply              # promote the winning profile to production
python -m adk_agent optimize --show               # inspect the active profile
python -m adk_agent optimize --revert             # back to the untouched 'full' prompt
```

- **Profiles** (`optimize/profiles.py`): a `PromptProfile` bundles levers — the 4
  heavy static prompt blocks (`full`/`compact`/`off`), section-prune threshold,
  **model routing**, **entity-map grounding**, thinking/output caps. The canonical
  `full` profile reproduces the production prompt **byte-for-byte** (the baseline).
- **Entity-map grounding** (`skills/entity_map.py`): a zero-LLM regex pre-pass that
  extracts survey/khata/date/amount/entry tokens and injects a `VERIFIED ENTITIES`
  block — to help a smaller model hold accuracy (langextract-style grounding).
- **Harness + gate** (`optimize/harness.py`, `optimize/gate.py`): each profile is
  run through the real extractor; the gate accepts it **only if** field/entry/type
  accuracy is non-decreasing **and** estimated USD cost (or latency) drops.
- **Loop** (`optimize/loop.py`): greedily compounds accepted levers, writes
  `optimize/artifacts/{leaderboard.jsonl,report.md,best_profile.json}`, and
  `--apply` promotes the winner to `active_profile.json` (every run reads it via
  `pipeline._load_active_profile`; reversible). Deterministic + bounded.

**Important — offline vs live:** with `--dry-run` (or no key) the FakeGemini returns
a fixed payload, so **token/cost savings are real but accuracy is parity-only**.
Validate any compaction/model lever against golden cases or a live key before you
`--apply`.

---

## Live validation results (sample PDF, your key, frugal)

| profile | model | latency | $/doc | entry recall vs pro |
| --- | --- | --- | --- | --- |
| baseline | gemini-3.1-pro | 44.6 s | $0.091 | 1.00 |
| flash only | gemini-3.5-flash | **17.9 s** | **$0.043** | **0.60** ⚠️ |
| flash + grounding + compact | gemini-3.5-flash | 31 s | $0.070 | 0.60 ⚠️ |

Flash is clearly cheaper/faster, but it **drops real entries**. The gate blocks it.

---

## Ground truth: what exists, and the flash question

**There are no machine-readable ground-truth files in the repo.** The golden eval
set (`adk_agent/eval/golden.evalset.json`) is gitignored and only created by
`feedback import` — nothing imported yet. `ground_truth.example.json` is a
synthetic template (doesn't even match the repo PDF).

**BUT** [`LAWYER_REVIEW_NOTES_2026_05_20.md`](LAWYER_REVIEW_NOTES_2026_05_20.md) is
a real human audit of the Trambo-150 TSR. It establishes the **true entry set**:

> **125, 243, 721, 905, 983** — which is *exactly* what `gemini-3.1-pro` extracted.

This independently validates the live finding:

- `gemini-3.1-pro` entry set **= lawyer truth** ✅
- `gemini-3.5-flash` missed entries (recall 0.60) — a **real regression** ❌
- the regex entry-detector was **wrong** (105/160/223 are false positives — 105 is
  a survey-number typo *inside* entry 905's body, not an entry; it missed 243/905).
  ⇒ the deterministic grounding can't be trusted to *force* an entry list; it is
  (now) a soft hint only.

The lawyer review also gives field-level truth for the hard entries (721 lifetime
distribution rows; 905 survey-format `105/p1` not `105/p1/p`; 983 inheritance —
death date `15/07/2021`, cert `D2021...`, heirs Shantiben/wife/57, Vasant/son/37,
Yogesh/son/34, supporting docs). That is enough to hand-build the **first real
golden case**.

Per that same review (and confirmed by the live test): **hold off on flash for the
main extractor.** Pro already misses facts; flash is worse. Safer use of flash:
captcha/translation models, not the main extractor — until golden cases say
otherwise.

---

## Recommended next steps (in priority order)

1. **Seed the first golden case from the lawyer review.** Transcribe the
   Trambo-150 corrections into a `ground_truth.json`, then:
   ```bash
   python -m adk_agent --pdf Kutch_Abdasa_Trambo_150_Original.pdf --out /tmp/trambo.docx
   python -m adk_agent feedback import --run <run_id> --truth ground_truth.json
   ```
   This (a) distils prompt guidelines from the corrections and (b) creates the
   first golden case, so `optimize` can finally score candidates on **real
   accuracy** instead of parity. *(I can do the transcription on request.)*

2. **Apply the lawyer review's prompt fixes** (accuracy, not efficiency — but they
   also make a smaller model viable): inheritance must keep death date + per-heir
   `(relationship, age)`; partition/lifetime-distribution must emit one row per
   source row (no merging solo+joint); survey format `પૈકી N પૈકી area` →
   `Survey N/p1 — area`. See `LAWYER_REVIEW_NOTES_2026_05_20.md` §"Recommended code
   changes". These belong in `tsr_generator/extractors/unified_extractor.py`'s
   prompt constants (and flow into the optimizer's `full` baseline automatically).

3. **Strengthen the deterministic entry detector** (`_identify_entry_numbers_fast`
   / `entity_map.build_entity_map`) — it had false positives + false negatives on
   Trambo-150. A reliable entry/owner/khata extractor is what would let the gate
   *accept* a grounded flash profile.

4. **Re-run `optimize` with the golden case + your key**, then `--apply` only if a
   profile clears the gate. With true accuracy in the loop, flash may well pass.

5. **(Later) local OCR** — only if scanned/image PDFs appear; the current sample
   has a clean text layer, so OCR is not today's bottleneck.

---

## File map (what's new)

```
adk_agent/optimize/
  profiles.py     PromptProfile, levers, model pricing/cost, active-profile persistence
  dataset.py      golden + parity evaluation corpus
  harness.py      run a profile -> accuracy + tokens + latency + cost
  gate.py         no-regression gate (accuracy held AND cost/latency down)
  loop.py         greedy lever search + leaderboard/report + promote/revert/show
adk_agent/skills/entity_map.py   deterministic entity-grounding "tool"
tests/test_adk_optimize.py       14 offline tests (profiles, gate, entity-map, cost, loop)
```

Run all tests: `pytest -q` (offline, no key). Optimizer only:
`pytest tests/test_adk_optimize.py -q`.

---

## Secret hygiene

The Gemini key you provided this session was used **in-process only** for the live
validation — it is in **no file or commit** (verified by secret scan). Because it
appears in the chat transcript, **please rotate it.** Note: a different key
(`AIzaSy…`) is referenced in `LAWYER_REVIEW_NOTES_2026_05_20.md` as living in a
local `.env` (gitignored, not in this container).
