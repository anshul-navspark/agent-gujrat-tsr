# QM skills

Three skills for Nav Law staff to run Gujarat land work from Slack via
**QM (Quartermaster)**, YC's open-source agent harness.

| Skill | Input | Output |
|---|---|---|
| `gujarat-tsr` | district, taluka, village, survey no. | draft TSR `.docx` — **the normal path** |
| `gujarat-land-record` | same | the AnyRoR record PDF only |
| `gujarat-tsr-from-pdf` | a land-record PDF | draft TSR `.docx` |

## Why every name starts with `gujarat-`

QM's skill list is global across packs. Rajasthan lives in its own repo
(`agent-raj-tsr`) and will register as its own pack, so a bare `tsr` or
`land-record` here would collide with its equivalent the day it lands — and a
lawyer in Slack would get whichever matched first, silently.

The two states share almost nothing worth abstracting: different portal, different
language, different identifiers (survey number vs khasra/khata), different
extraction rules. They are deliberately separate repos and separate packs. What
they *do* share is the deliverable — same letterhead, same four-table skeleton —
but the overlap is a few hundred lines of Word plumbing, not enough to justify
merging two working codebases.

One thing worth knowing if you touch Rajasthan next: its output currently has **no
Word auto-numbering and no cross-references**. Gujarat gained both after the lawyer
found that deleting a chain-of-title row broke the numbering. Porting them is a
small, high-value job.

## How QM loads these

An admin registers this repo as a skill pack (`POST /api/skill-packs` with
`{url, ref}`), then imports it (`POST /api/skill-packs/:id/import`). Both are
admin-gated.

Two constraints from QM's ingest (`src/skills/ingest.ts`) that shape these bundles:

1. **Only the directory containing each `SKILL.md` is materialised.** The engine
   does not ride along, which is why every skill starts by running
   `scripts/ensure_env.sh` to clone this repo into the sandbox.
2. **A single binary file under a skill directory silently drops the whole skill**
   (`collectAssets` returns null). Keep these bundles text-only — no PDFs, no
   `.docx`, no images. If a skill mysteriously fails to import, check this first.

Pack fetch caps are 5000 files / 32 MB; this repo is far under both.

## Credentials (QM org keychain → sandbox env)

| Key | Needed by | Why |
|---|---|---|
| `GITHUB_TOKEN` | all three | this repo is private and the skill clones it |
| `ANYROR_PROXY` | fetch, tsr | the asocks Indian residential proxy. **Gateway port 443 only** — 8080 and 12321 return 407 and look like a dead subscription |

**No model API keys.** Captcha and extraction both use the host's Claude Code
subscription via `claude -p`. That is deliberate: all API credit balances are zero,
and it is the only free path to a model. The sandbox needs the `claude` CLI on PATH.

`GEMINI_API_KEY` is optional and unused on this path — the app boots and scrapes
without it (verified: full suite green, and a live fetch completed, with no key set).

## Host

Runs on the lawyer's own machine — awake when they are working, which is when they
need it — with Hemant's PC as a **warm standby**, not automatic failover.

Making the standby actually work:

- Both hosts run the same stack, kept in sync by `git pull`, each with a logged-in
  Claude Code subscription.
- **Keep jobs stateless.** A run is `village + survey → PDF → docx` and is
  idempotent, so nothing important lives in QM's database. Point `LOCAL_CACHE_DIR`
  at a shared location so both hosts see the same cached PDFs and neither refetches
  through the proxy. This is what makes switching hosts cheap.
- Failover is flipping a Cloudflare Tunnel to the standby. Neither machine has a
  public URL, so a tunnel (or QM's Socket Mode) is required regardless — it also
  sidesteps the office CGNAT block.
- **Rehearse the switch once.** A two-host setup nobody has tested is a one-host
  setup with extra steps.

Note the Mac sleeps; use `caffeinate` or Energy Saver while it is serving.

## Setting up a fresh clone

`.env` is **not** in the repo and will not come with a clone — it was tracked until
2026-08-27 and leaked four API keys. Copy `.env.example` if you need it. Nothing on
the zero-credit path does.

## Read before changing how AnyRoR is called

`references/anyror-operations.md`. AnyRoR blocks by source IP, the firm has one
proxy exit, and a block affects everyone at once.
