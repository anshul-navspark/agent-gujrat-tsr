"""
Ground-truth feedback loop.

Closes the loop from a human lawyer's corrections back into the system:

    run -> extraction.json -> (lawyer fixes) -> ground_truth.json
        -> diff(model, truth) -> corrections
        -> (a) learned prompt guidelines  -> injected into the extraction prompt
        -> (b) ADK golden eval case        -> measures regression/improvement

Entry point: :func:`adk_agent.feedback.import_fixes.import_fixes`.
"""

from adk_agent.feedback.diff import Correction, diff_extractions
from adk_agent.feedback.ground_truth import load_extraction, load_ground_truth
from adk_agent.feedback.import_fixes import import_fixes

__all__ = [
    "Correction",
    "diff_extractions",
    "load_extraction",
    "load_ground_truth",
    "import_fixes",
]
