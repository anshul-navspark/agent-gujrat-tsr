"""
Evaluation — golden dataset (ground truth) + structured field-accuracy eval.

* :mod:`adk_agent.eval.evalset` maintains ``golden.evalset.json`` (ADK evalset
  shape) built from lawyer-reviewed runs.
* :mod:`adk_agent.eval.run_eval` re-runs extraction over the golden cases and
  scores it against ground truth (field accuracy, entry recall, type accuracy),
  giving a single regression-tracking number for prompt changes.
"""

from adk_agent.eval.evalset import load_golden_cases, upsert_golden_case
from adk_agent.eval.run_eval import evaluate_golden, score_extraction

__all__ = [
    "load_golden_cases",
    "upsert_golden_case",
    "evaluate_golden",
    "score_extraction",
]
