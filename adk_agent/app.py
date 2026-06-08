"""
ADK ``App`` + ``Runner`` construction.

Bundles a root agent (either the bare extractor agent for the *pipeline* engine,
or the full graph ``Workflow`` for the *graph* engine) with the global
:class:`ObservabilityPlugin`, and exposes a configured in-memory runner.
"""

from __future__ import annotations

from typing import Union

from google.adk import Agent
from google.adk.apps import App
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import InMemoryRunner

from adk_agent.config import AdkConfig
from adk_agent.dry_run_model import FakeGemini
from adk_agent.observability import ObservabilityPlugin


def resolve_model(config: AdkConfig, profile=None) -> Union[str, BaseLlm]:
    """
    Return the model for ADK agents: the offline fake, or the Gemini model id.

    A prompt *profile* may route to a different Gemini model (``model_name``);
    in dry-run/offline mode the FakeGemini is always used regardless.
    """
    model_name = (getattr(profile, "model_name", None) or config.model_name)
    if config.dry_run or not config.has_api_key:
        return FakeGemini(model="fake-" + model_name)
    return model_name


def build_app(config: AdkConfig, root_agent, *, app_name: str = None) -> App:
    """Wrap *root_agent* in an ``App`` with the observability plugin attached."""
    return App(
        name=app_name or config.app_name,
        root_agent=root_agent,
        plugins=[ObservabilityPlugin()],
    )


def make_runner(app: App) -> InMemoryRunner:
    """Create an in-memory runner for *app* (in-memory session/artifact services)."""
    return InMemoryRunner(app=app)
