"""
Configuration for the ADK TSR workflow.

Intentionally thin: it reuses the *existing* environment variables (so the ADK
workflow stays in lock-step with the legacy pipeline) and adds only the few
settings the agent layer needs (filesystem locations for run records, learned
guidelines and the golden eval set).

Per the project decision, the ADK workflow targets **Gemini** natively through
ADK's `google-genai` integration. ADK's Gemini backend authenticates from
``GOOGLE_API_KEY`` or ``GEMINI_API_KEY``; we bridge the latter to the former so
the existing ``GEMINI_API_KEY`` keeps working unchanged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Repository root (…/adk_agent/config.py -> repo root).
REPO_ROOT = Path(__file__).resolve().parent.parent

# Where the ADK app, learned guidelines and golden eval set live.
ADK_PKG_DIR = Path(__file__).resolve().parent


def _bridge_gemini_api_key() -> str:
    """ADK's Gemini backend reads GOOGLE_API_KEY first; mirror GEMINI_API_KEY."""
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
    if key:
        os.environ.setdefault("GOOGLE_API_KEY", key)
        os.environ.setdefault("GEMINI_API_KEY", key)
    # ADK / google-genai: use the public Gemini API, not Vertex, unless told.
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "0")
    return key


@dataclass
class AdkConfig:
    """Resolved configuration for an ADK workflow run."""

    # --- Model ---
    # Reuse the same model the legacy extractor uses so behaviour matches.
    model_name: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-pro-preview")
    )
    api_key: str = field(default_factory=_bridge_gemini_api_key)
    temperature: float = 0.0
    # Gemini-3 "thinking" budget knob, kept consistent with the legacy extractor.
    thinking_level: Optional[str] = field(
        default_factory=lambda: (os.getenv("GEMINI_THINKING_LEVEL", "low").strip().lower() or None)
    )

    # --- App identity ---
    app_name: str = "gujarat_tsr_adk"
    user_id: str = "tsr_pipeline"

    # --- Filesystem layout ---
    # Run records (one folder per pipeline run): prompts, responses, tokens, DOCX.
    runs_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("ADK_RUNS_DIR", str(ADK_PKG_DIR / "runs"))
        )
    )
    # Learned prompt guidelines distilled from lawyer corrections.
    guidelines_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("ADK_GUIDELINES_PATH", str(ADK_PKG_DIR / "feedback" / "prompting_guidelines.jsonl"))
        )
    )
    # Human-readable rendering of the guidelines (regenerated on every import).
    guidelines_md_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("ADK_GUIDELINES_MD_PATH", str(ADK_PKG_DIR / "feedback" / "prompting_guidelines.md"))
        )
    )
    # ADK golden eval set (ground-truth captured from lawyer-reviewed runs).
    golden_evalset_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("ADK_GOLDEN_EVALSET", str(ADK_PKG_DIR / "eval" / "golden.evalset.json"))
        )
    )
    # Optimizer artifacts: leaderboards, reports, baseline cache (gitignored).
    optimize_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("ADK_OPTIMIZE_DIR", str(ADK_PKG_DIR / "optimize" / "artifacts"))
        )
    )
    # The promoted "winning" prompt profile every run reads (None until promoted).
    active_profile_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("ADK_ACTIVE_PROFILE", str(ADK_PKG_DIR / "optimize" / "active_profile.json"))
        )
    )

    # --- Behaviour ---
    dry_run: bool = False  # use the offline FakeGemini model (no API key needed)
    headless: bool = field(default_factory=lambda: os.getenv("HEADLESS", "true").lower() != "false")

    def ensure_dirs(self) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.guidelines_path.parent.mkdir(parents=True, exist_ok=True)
        self.golden_evalset_path.parent.mkdir(parents=True, exist_ok=True)
        self.optimize_dir.mkdir(parents=True, exist_ok=True)

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)


_config: Optional[AdkConfig] = None


def get_adk_config(refresh: bool = False, **overrides) -> AdkConfig:
    """Return the process-wide :class:`AdkConfig` (lazily constructed)."""
    global _config
    if _config is None or refresh or overrides:
        _config = AdkConfig(**overrides)
        _config.ensure_dirs()
    return _config
