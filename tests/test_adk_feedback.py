"""
Tests for the ground-truth feedback loop and eval scoring.

Pure data-flow tests — no model calls, no network.
"""

import json
from pathlib import Path

import pytest

from adk_agent.config import get_adk_config
from adk_agent.eval.evalset import load_golden_cases
from adk_agent.eval.run_eval import score_extraction
from adk_agent.feedback.diff import diff_extractions
from adk_agent.feedback.guidelines_store import render_guidelines_for_prompt
from adk_agent.feedback.import_fixes import import_fixes


@pytest.fixture
def adk_cfg(tmp_path):
    cfg = get_adk_config(
        refresh=True,
        dry_run=True,
        runs_dir=tmp_path / "runs",
        guidelines_path=tmp_path / "guidelines.jsonl",
        guidelines_md_path=tmp_path / "guidelines.md",
        golden_evalset_path=tmp_path / "golden.evalset.json",
    )
    yield cfg
    get_adk_config(refresh=True)


def _entry(num, type_, desc, **kw):
    base = {"entry_number": num, "type": type_, "description": desc}
    base.update(kw)
    return base


def test_diff_detects_field_entry_and_membership_changes():
    model = {
        "land_details": {"owner": "Mer Deva"},
        "entry_numbers": ["1", "9"],
        "mutation_entries": [
            _entry("1", "SALE", "x"),
            _entry("9", "ORDER", "spurious"),
        ],
    }
    truth = {
        "land_details": {"owner": "Mer Deva Rabari"},
        "entry_numbers": ["1", "2"],
        "mutation_entries": [
            _entry("1", "LOAN", "x", certification_status="rejected"),
            _entry("2", "DEATH", "y"),
        ],
    }
    kinds = sorted(c.kind for c in diff_extractions(model, truth))
    assert "land_field" in kinds          # owner changed
    assert "entry_type" in kinds          # entry 1 SALE -> LOAN
    assert "certification" in kinds       # entry 1 certification_status
    assert "missing_entry" in kinds       # entry 2 absent from model
    assert "extra_entry" in kinds         # entry 9 absent from truth


def test_identical_extraction_scores_perfectly():
    x = {
        "land_details": {"owner": "A", "village_name": "V"},
        "entry_numbers": ["1"],
        "mutation_entries": [_entry("1", "SALE", "d", entry_status="certified")],
    }
    score = score_extraction(x, x)
    assert score["field_accuracy"] == 1.0
    assert score["entry_recall"] == 1.0
    assert score["type_accuracy"] == 1.0
    assert score["num_corrections"] == 0


def test_import_fixes_writes_guidelines_and_golden(adk_cfg, tmp_path):
    # Build a minimal completed run on disk.
    run_dir = adk_cfg.runs_dir / "r1"
    run_dir.mkdir(parents=True)
    model = {
        "land_details": {"owner": "Mer Deva"},
        "entry_numbers": ["1"],
        "mutation_entries": [_entry("1", "SALE", "That A sold ...")],
    }
    (run_dir / "extraction.json").write_text(json.dumps(model), encoding="utf-8")
    (run_dir / "record.json").write_text(json.dumps({"inputs": {"survey": None}}), encoding="utf-8")
    (run_dir / "source.txt").write_text("LAND RECORD DOC TEXT", encoding="utf-8")

    truth = {
        "land_details": {"owner": "Mer Deva Rabari"},
        "entry_numbers": ["1"],
        "mutation_entries": [_entry("1", "LOAN", "That A took a loan ...")],
    }
    truth_path = tmp_path / "gt.json"
    truth_path.write_text(json.dumps(truth), encoding="utf-8")

    report = import_fixes(adk_cfg, run="r1", truth=str(truth_path))

    assert report["num_corrections"] >= 2
    assert Path(adk_cfg.guidelines_path).exists()
    assert Path(adk_cfg.guidelines_md_path).exists()
    assert Path(adk_cfg.golden_evalset_path).exists()

    # Guidelines are renderable for prompt injection.
    rendered = render_guidelines_for_prompt(adk_cfg)
    assert "LOAN" in rendered or "owner" in rendered

    # The corrected run became a golden case (with the source doc for replay).
    cases = load_golden_cases(adk_cfg)
    assert len(cases) == 1
    assert cases[0]["eval_id"] == "r1"
    assert cases[0]["pdf_text"] == "LAND RECORD DOC TEXT"


def test_guidelines_dedupe_increments_count(adk_cfg, tmp_path):
    """Re-importing the same flavour of correction collapses into one guideline."""
    from adk_agent.feedback.guidelines_store import load_guidelines, upsert_guidelines, synthesize_guideline
    from adk_agent.feedback.diff import Correction

    c = Correction(scope="land_details", field="owner", kind="land_field",
                   model_value="A", truth_value="B")
    g = synthesize_guideline(c, source_run="run1")
    upsert_guidelines(adk_cfg.guidelines_path, [g])
    g2 = synthesize_guideline(c, source_run="run2")
    merged = upsert_guidelines(adk_cfg.guidelines_path, [g2])

    owner_guidelines = [x for x in merged if x.field == "owner"]
    assert len(owner_guidelines) == 1
    assert owner_guidelines[0].count == 2
    assert set(owner_guidelines[0].sources) == {"run1", "run2"}
