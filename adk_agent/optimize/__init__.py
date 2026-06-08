"""
Closed-loop extraction optimizer.

A bounded, resumable **measure -> gate -> promote** loop that drives down the
extractor's token usage and latency *without* regressing accuracy:

  * :mod:`adk_agent.optimize.profiles`  — parametric prompt *profiles* (compact /
    omit the heavy static prompt blocks, tighten section pruning, route the
    model, cap thinking / output). The canonical ``full`` profile reproduces the
    current production prompt byte-for-byte (the baseline).
  * :mod:`adk_agent.optimize.dataset`   — builds the evaluation corpus: lawyer
    ground truth where available, else parity-vs-current-production output.
  * :mod:`adk_agent.optimize.harness`   — runs a profile over the corpus and
    measures accuracy (field / entry / type) **and** tokens + latency.
  * :mod:`adk_agent.optimize.gate`      — the no-regression gate: a candidate is
    accepted only if accuracy holds and tokens/latency drop.
  * :mod:`adk_agent.optimize.loop`      — greedy lever search + leaderboard +
    report; promotes the winner to ``active_profile.json`` (which every run then
    uses) and is fully reversible.

Run it with ``python -m adk_agent optimize`` (offline-capable with ``--dry-run``).
"""

from adk_agent.optimize.profiles import (  # noqa: F401
    FULL_PROFILE,
    PromptProfile,
    build_prompt,
    load_active_profile,
    save_active_profile,
)
