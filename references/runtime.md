# The runtime floor: Python >= 3.11

Read before changing a Dockerfile, a CI matrix, a venv, or `ensure_env.sh`.

**3.11 is not a preference or a compromise. It is the number every layer already
agrees on, and the QM sandbox is what decides it.**

| Layer | Python | Source |
|---|---|---|
| QM sandbox | **3.11.2** | `debian:12-slim` (digest-pinned) in QM's `fly/Dockerfile` |
| This repo's Docker | 3.11 | `FROM python:3.11-slim` |
| CI | 3.11 | `.github/workflows/ci.yml`, `python-version: "3.11"` |
| `venv/` | 3.11.15 **but see below** | local, and internally inconsistent |
| **This Mac's bare `python3`** | **3.9.6** | `/usr/bin/python3` — the only outlier |

**VERIFIED 2026-08-29** by running the built images. `qm-sandbox-base:dev` and
`qm-sandbox-local:latest` both report `Python 3.11.2` and carry `/usr/bin/python3.11`
only — **no 3.12, no 3.13**. Raising the floor above 3.11 would fail every skill run
with no fallback to find. The Nav Law image (`local/Dockerfile.navlaw`) adds chromium,
poppler and Indic fonts on top of that base; it does not add a Python.

## The local `venv/` is a mongrel — rebuild it

Found 2026-08-29. `venv/bin/python` runs **3.11.15**, but the venv was **created by
3.9.6 and relinked afterwards**:

```
venv/pyvenv.cfg          version = 3.9.6
                         home = /Library/Developer/CommandLineTools/usr/bin
venv/bin/python       -> python3.11  -> homebrew 3.11.15   (Jan 24)
venv/bin/python3.9    -> python3     -> ALSO 3.11.15       (Feb 6)
venv/lib/python3.9/site-packages     0 entries
venv/lib/python3.11/site-packages    274 entries
```

It functions — imports resolve, the suite passes — but the metadata is wrong in two
ways that will bite someone:

1. Anything that reads `pyvenv.cfg` rather than running the binary (IDEs, tooling,
   `python -m venv --upgrade`) is told 3.9.6.
2. `venv/bin/python3.9` **is 3.11**. Anyone reaching for it to reproduce a 3.9 bug
   gets a silent 3.11 answer.

`venv/` is gitignored, so this is a local dev artifact and not something shipped.
The fix is to delete and rebuild it with an explicit `python3.11 -m venv venv`. Do
not "repair" it by editing `pyvenv.cfg`.

## `>= 3.11`, never `== 3.11.x`

The sandbox says 3.11.2 and a Mac venv says 3.11.15. **These do not conflict.**
Within one minor series Python guarantees no syntax change, no stdlib API removal,
and a stable ABI — both are `cp311`, so identical wheels install on both.

Nor is the sandbox stale: Debian freezes the upstream version number and backports
security fixes into it, so the package is `3.11.2-6+deb12u8`, built 2026-05-12.

*The residual difference:* Debian backports security fixes, not every upstream
bugfix. A pure bugfix landed between 3.11.2 and 3.11.15 could behave differently in
the sandbox than on a Mac. Small — but it is why the sandbox is the reference
environment and a developer Mac is not.

## Two traps that have already cost time

1. **`python3` on this Mac is a shell alias to 3.11, and a script does not inherit
   it.** Prefix a command with `timeout`, `env`, or `PATH=...` and it execs
   `/usr/bin/python3` — **3.9.6**. So `timeout python3 -m pytest` and
   `python3 -m pytest` run *different interpreters* with *different installed
   packages*. Run the suite explicitly:
   `/opt/homebrew/bin/python3.11 -m pytest -q -m "not integration"`.
   (A related symptom: under 3.9, `pytest -W error::DeprecationWarning` segfaults in
   `pymupdf`'s SWIG module. That is the interpreter, not our code.)
2. **`ensure_env.sh` used to do `python3 -m venv`.** Inside the sandbox that resolves
   to 3.11 and is correct — but only by coincidence of the base image. The scripts now
   select an interpreter explicitly and fail loudly, so a future QM base bump is a
   loud change rather than a silent one.

## When to revisit

**Trigger on QM's base image moving, not on Python's release schedule.** Debian 13
ships Python 3.13; when QM moves, the sandbox interpreter changes underneath us.

A bump before then buys support window this codebase cannot spend — it uses no
language feature above 3.11 — while breaking the one environment a lawyer actually
runs. When the trigger fires, **check wheels first**: `pymupdf` is the binding
constraint here (a SWIG/C extension), and the streamlit stack after it. The sibling
`agent-mp` repo is pure-Python and unconstrained, so move the two together rather
than letting them drift.
