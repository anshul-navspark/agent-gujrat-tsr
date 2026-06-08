"""
Tests for the closed-loop extraction optimizer.

All offline (dry-run FakeGemini, no key, no network). FakeGemini returns a fixed
extraction regardless of the prompt, so every profile yields identical accuracy
— which is exactly what makes the *no-regression* invariant easy to assert: the
loop may only ever trade equal accuracy for fewer tokens.
"""

import asyncio
from pathlib import Path

import pytest

from adk_agent.config import get_adk_config
from adk_agent.eval.evalset import upsert_golden_case
from adk_agent.optimize.gate import RegressionGate
from adk_agent.optimize.harness import ProfileResult
from adk_agent.optimize.loop import promote_best, revert_active, run_optimization, show_active
from adk_agent.optimize.profiles import FULL_PROFILE, PromptProfile, build_prompt
from adk_agent.skills.extraction import build_extraction_prompt

SAMPLE_TEXT = (
    "Land Details\nVillage: Keshav\nTaluka: Abdasa\nDistrict: Kutch\n"
    "Survey Number: 150/p1\nTotal Area: 1-88-48\n" + ("Entry Details\n101\n102\n103\n" * 30)
)

TRUTH = {
    "land_details": {
        "village_name": "Keshav", "taluka_name": "Abdasa", "district_name": "Kutch",
        "survey_number": "150/p1", "old_survey_number": "", "total_area": "1-88-48",
        "nature_of_land": "New Tenure, Agricultural", "owner": "Mer Deva Depa",
    },
    "entry_numbers": ["101", "102", "103"],
    "mutation_entries": [
        {"entry_number": "101", "type": "SALE", "description": "That ... sold ...",
         "entry_status": "certified"},
        {"entry_number": "102", "type": "LOAN", "description": "That ... took a loan ...",
         "entry_status": "certified"},
        {"entry_number": "103", "type": "NOT RELATED",
         "description": "This Entry is not related to Present Survey Number."},
    ],
}


@pytest.fixture
def adk_cfg(tmp_path):
    cfg = get_adk_config(
        refresh=True,
        dry_run=True,
        runs_dir=tmp_path / "runs",
        guidelines_path=tmp_path / "g.jsonl",
        guidelines_md_path=tmp_path / "g.md",
        golden_evalset_path=tmp_path / "golden.json",
        optimize_dir=tmp_path / "art",
        active_profile_path=tmp_path / "active.json",
    )
    yield cfg
    get_adk_config(refresh=True)


# --------------------------------------------------------------------- profiles
def test_full_profile_is_byte_identical_to_production_prompt():
    assert FULL_PROFILE.is_canonical_full()
    assert build_prompt(SAMPLE_TEXT, "", FULL_PROFILE) == build_extraction_prompt(SAMPLE_TEXT, "")


def test_compact_and_off_profiles_shrink_the_prompt():
    full = build_prompt(SAMPLE_TEXT, "", FULL_PROFILE)
    compact = build_prompt(
        SAMPLE_TEXT, "",
        PromptProfile(name="c", description_examples="compact", formatting_rules="compact"),
    )
    off = build_prompt(
        SAMPLE_TEXT, "",
        PromptProfile(name="o", description_examples="off", formatting_rules="off",
                      entry_type_rules="off", certification_patterns="off"),
    )
    assert len(compact) < len(full)
    assert len(off) < len(compact)
    # Even stripped down, it is still a valid extraction prompt.
    for piece in ("DOCUMENT TEXT", "mutation_entries", "land_details"):
        assert piece in off


def test_prune_threshold_trims_long_documents():
    big = "x" * 40000 + "\nEntry Details\n101\n"
    full = build_prompt(big, "", FULL_PROFILE)              # threshold 15000
    pruned = build_prompt(big, "", PromptProfile(name="p", prune_threshold=6000))
    assert len(pruned) < len(full)


# ------------------------------------------------------------------------- gate
def _result(profile, *, field=1.0, recall=1.0, type_=1.0, tokens=1000.0, latency=10.0, cost=None):
    return ProfileResult(
        profile=profile, n_cases=1, field_accuracy=field, entry_recall=recall,
        type_accuracy=type_, avg_prompt_tokens=tokens, avg_total_tokens=tokens,
        avg_thinking_tokens=0.0, avg_latency_ms=latency,
        avg_cost_usd=(cost if cost is not None else tokens * 1e-5),
    )


def test_gate_rejects_accuracy_regression_even_with_big_savings():
    gate = RegressionGate(min_token_saving_pct=1.0)
    d = gate.evaluate(_result(FULL_PROFILE, tokens=1000),
                      _result(PromptProfile(name="x"), field=0.9, tokens=400))
    assert not d.accepted
    assert not d.accuracy_ok


def test_gate_accepts_equal_accuracy_cost_saver():
    gate = RegressionGate(min_token_saving_pct=1.0)
    d = gate.evaluate(_result(FULL_PROFILE, tokens=1000),
                      _result(PromptProfile(name="x"), tokens=700))
    assert d.accepted and d.accuracy_ok and d.efficiency_win
    assert d.cost_delta_pct < 0


def test_gate_accepts_cheaper_model_at_equal_tokens():
    """Routing to a cheaper model wins on cost even when token counts are equal."""
    gate = RegressionGate(min_token_saving_pct=1.0)
    base = _result(FULL_PROFILE, tokens=1000, cost=0.012)        # pro
    flash = _result(PromptProfile(name="flash"), tokens=1000, cost=0.009)  # flash, same tokens
    d = gate.evaluate(base, flash)
    assert d.accepted and d.accuracy_ok
    assert d.cost_delta_pct < 0 and abs(d.token_delta_pct) < 1e-9


def test_gate_rejects_when_no_efficiency_win():
    gate = RegressionGate(min_token_saving_pct=1.0)
    d = gate.evaluate(_result(FULL_PROFILE, tokens=1000),
                      _result(PromptProfile(name="x"), tokens=1000))
    assert not d.accepted and d.accuracy_ok and not d.efficiency_win


# ----------------------------------------------------------- entity-map + cost
def test_entity_map_extracts_structured_tokens():
    from adk_agent.skills.entity_map import build_entity_map

    text = "land bearing Survey No. 150/p1(215), 389(215), 373/p1 sold for Rs. 2,50,000/- on 14/05/2001"
    emap = build_entity_map(text)
    assert "150/p1(215)" in emap["survey_numbers"]
    assert "389(215)" in emap["survey_numbers"]
    assert "215" in emap["khata_numbers"]
    assert "14/05/2001" in emap["dates"]
    assert "2,50,000" in emap["amounts"]


def test_entity_map_profile_injects_grounding_block():
    grounded = build_prompt(
        SAMPLE_TEXT + "\nSurvey No. 150/p1(215) on 14/05/2001", "",
        PromptProfile(name="g", entity_map=True),
    )
    plain = build_prompt(SAMPLE_TEXT, "", PromptProfile(name="p"))
    assert "VERIFIED ENTITIES" in grounded
    assert "VERIFIED ENTITIES" not in plain


def test_estimate_cost_flash_cheaper_than_pro():
    from adk_agent.optimize.profiles import estimate_cost

    pro = estimate_cost("gemini-3.1-pro-preview", 10_000, 2_000)
    flash = estimate_cost("gemini-3.5-flash", 10_000, 2_000)
    flash_fake = estimate_cost("fake-gemini-3.5-flash", 10_000, 2_000)  # offline name
    assert flash < pro
    assert flash_fake == flash  # the 'fake-' prefix is stripped


# ------------------------------------------------------------------------- loop
def test_loop_finds_savings_without_accuracy_regression(adk_cfg):
    upsert_golden_case(adk_cfg, "case1", TRUTH, pdf_text=SAMPLE_TEXT)
    upsert_golden_case(adk_cfg, "case2", TRUTH, pdf_text=SAMPLE_TEXT + "\n# variant")

    report = asyncio.run(run_optimization(adk_cfg, include_sample=False))

    assert report["cases"] == 2
    b, w = report["baseline"], report["winner"]
    # The invariant: the winner never regresses accuracy vs the baseline.
    assert report["accuracy_held"] is True
    assert w["field_accuracy"] >= b["field_accuracy"] - 1e-9
    assert w["entry_recall"] >= b["entry_recall"] - 1e-9
    assert w["type_accuracy"] >= b["type_accuracy"] - 1e-9
    # And it actually saves cost/tokens (compact prompt blocks + model routing).
    assert report["cost_savings_pct"] > 0
    assert report["token_savings_pct"] > 0
    assert w["avg_total_tokens"] < b["avg_total_tokens"]
    assert w["avg_cost_usd"] < b["avg_cost_usd"]
    assert report["accepted_levers"]

    art = Path(adk_cfg.optimize_dir)
    for fname in ("leaderboard.jsonl", "best_profile.json", "report.md", "last_report.json"):
        assert (art / fname).exists(), fname


def test_loop_with_no_cases_is_graceful(adk_cfg):
    report = asyncio.run(run_optimization(adk_cfg, include_sample=False, include_golden=False))
    assert report["cases"] == 0
    assert "note" in report


def test_promote_and_revert_roundtrip(adk_cfg):
    upsert_golden_case(adk_cfg, "case1", TRUTH, pdf_text=SAMPLE_TEXT)
    asyncio.run(run_optimization(adk_cfg, include_sample=False))

    assert show_active(adk_cfg) is None
    promoted = promote_best(adk_cfg)
    assert promoted is not None and Path(adk_cfg.active_profile_path).exists()
    active = show_active(adk_cfg)
    assert active is not None and not active.is_canonical_full()

    assert revert_active(adk_cfg) is True
    assert show_active(adk_cfg) is None


def test_promoted_profile_is_used_by_subsequent_runs(adk_cfg, tmp_path):
    upsert_golden_case(adk_cfg, "case1", TRUTH, pdf_text=SAMPLE_TEXT)
    asyncio.run(run_optimization(adk_cfg, include_sample=False))
    promote_best(adk_cfg)

    from adk_agent.pipeline import extract_only_record

    # use_active_profile=True (default) should pick up the promoted compact profile.
    _, rec_active = asyncio.run(extract_only_record(adk_cfg, SAMPLE_TEXT))
    _, rec_full = asyncio.run(
        extract_only_record(adk_cfg, SAMPLE_TEXT, profile=FULL_PROFILE, use_active_profile=False)
    )
    assert rec_active.token_totals["prompt_tokens"] < rec_full.token_totals["prompt_tokens"]
