"""
Integration tests for the ADK TSR workflow.

All tests run fully offline using the dry-run FakeGemini model (no API key, no
network), exercising both orchestration engines end-to-end against the sample
land-record PDF and asserting on the observability run record.
"""

import asyncio
from pathlib import Path

import pytest

from adk_agent.config import get_adk_config
from adk_agent.pipeline import run_pipeline

REPO = Path(__file__).resolve().parent.parent
SAMPLE_PDF = REPO / "Kutch_Abdasa_Trambo_150_Original.pdf"


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
    get_adk_config(refresh=True)  # reset global config for other tests


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="sample PDF not present")
@pytest.mark.parametrize("engine", ["pipeline", "graph"])
def test_e2e_dry_run_produces_docx(adk_cfg, tmp_path, engine):
    out = tmp_path / "out.docx"
    record = asyncio.run(
        run_pipeline(
            adk_cfg, mode="pdf", output_path=str(out), pdf_path=str(SAMPLE_PDF), engine=engine
        )
    )

    assert record.status == "success", record.error
    assert out.exists() and out.stat().st_size > 0
    assert record.output["entries_count"] >= 1

    # Observability captured the model call.
    assert len(record.llm_calls) >= 1
    call = record.llm_calls[0]
    assert call.prompt and "DOCUMENT TEXT" in call.prompt
    assert call.response_tokens > 0
    assert record.token_totals["total_tokens"] > 0

    # Skill steps recorded.
    skill_names = {s.name for s in record.skills}
    assert any("pdf_text" in n for n in skill_names)
    assert any("assemble" in n for n in skill_names)

    # Durable artifacts persisted.
    run_dir = record.run_dir(adk_cfg.runs_dir)
    for fname in ("record.json", "extraction.json", "trace.md", "source.txt"):
        assert (run_dir / fname).exists(), fname


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="sample PDF not present")
def test_engines_agree(adk_cfg, tmp_path):
    out_p = tmp_path / "p.docx"
    out_g = tmp_path / "g.docx"
    rec_p = asyncio.run(
        run_pipeline(adk_cfg, mode="pdf", output_path=str(out_p), pdf_path=str(SAMPLE_PDF), engine="pipeline")
    )
    rec_g = asyncio.run(
        run_pipeline(adk_cfg, mode="pdf", output_path=str(out_g), pdf_path=str(SAMPLE_PDF), engine="graph")
    )
    assert rec_p.output["entries_count"] == rec_g.output["entries_count"]
    assert rec_p.output["entry_types"] == rec_g.output["entry_types"]


def test_missing_input_pdf_fails_gracefully(adk_cfg, tmp_path):
    record = asyncio.run(
        run_pipeline(
            adk_cfg, mode="pdf", output_path=str(tmp_path / "o.docx"),
            pdf_path=str(tmp_path / "does-not-exist.pdf"), engine="pipeline",
        )
    )
    assert record.status == "error"
    assert record.error
    # The error is still persisted for debugging.
    assert (record.run_dir(adk_cfg.runs_dir) / "record.json").exists()
