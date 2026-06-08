"""
ObservabilityPlugin — a global ADK plugin that captures every model call.

Registered once on the ``App``/``Runner``, its callbacks fire for *every* agent
and model invocation in the workflow.  It records, into the current
:class:`RunContext`'s :class:`RunRecord`:

  * ``before_agent`` / ``after_agent``  -> a :class:`SkillStep` with timing,
  * ``before_model``                    -> the fully rendered prompt + start time,
  * ``after_model``                     -> the raw response, token usage, finish reason.

This is the data the prompt-improvement workflow reads back: the exact prompt
that produced a given (possibly wrong) extraction, alongside the lawyer-corrected
ground truth.

Callbacks never raise — observability must not break a run.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from google.adk.plugins.base_plugin import BasePlugin

from adk_agent.observability.run_context import current_run
from adk_agent.observability.run_record import LlmCall, SkillStep

logger = logging.getLogger(__name__)


def _content_text(content: Any) -> str:
    """Flatten a genai Content (or list) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_content_text(c) for c in content)
    parts = getattr(content, "parts", None)
    if not parts:
        return getattr(content, "text", "") or ""
    out: List[str] = []
    for p in parts:
        t = getattr(p, "text", None)
        if t:
            out.append(t)
    return "\n".join(out)


def _rendered_prompt(llm_request: Any) -> str:
    """Reconstruct the full prompt: system instruction + conversation contents."""
    sections: List[str] = []
    config = getattr(llm_request, "config", None)
    sys_inst = getattr(config, "system_instruction", None) if config else None
    if sys_inst:
        sections.append("=== SYSTEM INSTRUCTION ===\n" + _content_text(sys_inst))
    contents = getattr(llm_request, "contents", None) or []
    convo = "\n".join(_content_text(c) for c in contents)
    if convo.strip():
        sections.append("=== CONTENTS ===\n" + convo)
    return "\n\n".join(sections)


class ObservabilityPlugin(BasePlugin):
    """Captures agent timings and full model-call details into the run record."""

    def __init__(self, name: str = "tsr_observability"):
        super().__init__(name=name)
        # Correlate before_model -> after_model. Keyed by (invocation_id, agent).
        self._pending_model: Dict[Tuple[str, str], Tuple[LlmCall, float]] = {}
        self._pending_agent: Dict[Tuple[str, str], float] = {}

    # ------------------------------------------------------------------ agents
    async def before_agent_callback(self, *, agent, callback_context) -> None:
        try:
            key = (getattr(callback_context, "invocation_id", ""), getattr(agent, "name", ""))
            self._pending_agent[key] = time.monotonic()
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("before_agent_callback failed: %s", e)
        return None

    async def after_agent_callback(self, *, agent, callback_context) -> None:
        try:
            run = current_run()
            if run is None:
                return None
            name = getattr(agent, "name", "agent")
            key = (getattr(callback_context, "invocation_id", ""), name)
            start = self._pending_agent.pop(key, None)
            ms = int((time.monotonic() - start) * 1000) if start else 0
            run.record.add_skill(SkillStep(name=f"{name} (agent)", status="success", duration_ms=ms))
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("after_agent_callback failed: %s", e)
        return None

    # ------------------------------------------------------------------ models
    async def before_model_callback(self, *, callback_context, llm_request) -> None:
        try:
            agent_name = getattr(callback_context, "agent_name", "") or ""
            inv = getattr(callback_context, "invocation_id", "") or ""
            call = LlmCall(
                agent_name=agent_name,
                model=str(getattr(llm_request, "model", "") or ""),
                prompt=_rendered_prompt(llm_request),
            )
            self._pending_model[(inv, agent_name)] = (call, time.monotonic())
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("before_model_callback failed: %s", e)
        return None

    async def after_model_callback(self, *, callback_context, llm_response) -> None:
        try:
            # Ignore streaming partials; we only record the aggregated response.
            if getattr(llm_response, "partial", None):
                return None
            run = current_run()
            agent_name = getattr(callback_context, "agent_name", "") or ""
            inv = getattr(callback_context, "invocation_id", "") or ""
            pending = self._pending_model.pop((inv, agent_name), None)
            if pending is None:
                call, start = LlmCall(agent_name=agent_name), time.monotonic()
            else:
                call, start = pending
            call.duration_ms = int((time.monotonic() - start) * 1000)
            call.response_text = _content_text(getattr(llm_response, "content", None))
            fr = getattr(llm_response, "finish_reason", None)
            call.finish_reason = getattr(fr, "name", None) or (str(fr) if fr else "")
            if getattr(llm_response, "error_message", None):
                call.error = llm_response.error_message

            um = getattr(llm_response, "usage_metadata", None)
            if um is not None:
                call.prompt_tokens = getattr(um, "prompt_token_count", 0) or 0
                call.response_tokens = getattr(um, "candidates_token_count", 0) or 0
                call.thinking_tokens = getattr(um, "thoughts_token_count", 0) or 0
                call.total_tokens = getattr(um, "total_token_count", 0) or (
                    call.prompt_tokens + call.response_tokens
                )
            if not call.model:
                call.model = str(getattr(llm_response, "model_version", "") or "")

            if run is not None:
                run.record.add_llm_call(call)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("after_model_callback failed: %s", e)
        return None

    async def on_model_error_callback(self, *, callback_context, llm_request, error) -> None:
        try:
            run = current_run()
            if run is None:
                return None
            agent_name = getattr(callback_context, "agent_name", "") or ""
            run.record.add_llm_call(
                LlmCall(
                    agent_name=agent_name,
                    model=str(getattr(llm_request, "model", "") or ""),
                    prompt=_rendered_prompt(llm_request),
                    error=str(error),
                )
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("on_model_error_callback failed: %s", e)
        return None
