"""
FakeGemini — an offline ``BaseLlm`` for dry-runs, tests and CI.

It lets the *entire* ADK pipeline (graph wiring, observability plugin, DOCX
rendering, run records) execute end-to-end with **no API key and no network**,
by returning a deterministic, schema-valid :class:`UnifiedExtraction` payload.

Used by ``python -m adk_agent --dry-run`` and by the integration tests.  The
canned payload exercises the interesting downstream paths (an active LOAN with
no matching RELEASE -> an encumbrance finding; a certified SALE).
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Optional

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types as genai_types

# A representative, schema-valid extraction. Deterministic on purpose.
_DEFAULT_PAYLOAD = {
    "land_details": {
        "village_name": "Keshav",
        "taluka_name": "Abdasa",
        "district_name": "Kutch",
        "survey_number": "150/p1",
        "old_survey_number": "",
        "total_area": "1-88-48",
        "nature_of_land": "New Tenure, Agricultural",
        "owner": "Mer Deva Depa",
    },
    "entry_numbers": ["101", "102", "103"],
    "mutation_entries": [
        {
            "entry_number": "101",
            "date": "14/05/2001",
            "type": "SALE",
            "description": (
                "That Mer Deva Depa sold Survey No. 150/p1 measuring 1-88-48 Hectare "
                "to Mer Karshan Devshi for Rs. 2,50,000/- vide document no. 1234 dated 14/05/2001."
            ),
            "entry_status": "certified",
            "certification_status": "certified",
            "certification_official": "C.O. Abdasa",
            "certification_date": "20/05/2001",
        },
        {
            "entry_number": "102",
            "date": "10/03/2005",
            "type": "LOAN",
            "description": (
                "That Mer Karshan Devshi took a loan of Rs. 1,00,000/- on land bearing "
                "Survey No. 150/p1 from Bank of India, Naliya Branch."
            ),
            "entry_status": "certified",
            "certification_status": "certified",
            "certification_official": "C.O. Abdasa",
            "certification_date": "15/03/2005",
        },
        {
            "entry_number": "103",
            "date": "",
            "type": "NOT RELATED",
            "description": "This Entry is not related to Present Survey Number.",
            "entry_status": "",
            "certification_status": "",
            "certification_official": "",
            "certification_date": "",
        },
    ],
}

# Allow tests to swap the canned payload at runtime.
_payload_override: Optional[dict] = None


def set_dry_run_payload(payload: Optional[dict]) -> None:
    """Override (or reset, with ``None``) the canned extraction payload."""
    global _payload_override
    _payload_override = payload


class FakeGemini(BaseLlm):
    """A ``BaseLlm`` that returns a fixed JSON extraction without any network call."""

    def __init__(self, model: str = "fake-gemini", **kwargs):
        super().__init__(model=model, **kwargs)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        payload = _payload_override if _payload_override is not None else _DEFAULT_PAYLOAD
        text = json.dumps(payload, ensure_ascii=False)

        # Rough token accounting so the observability layer has something real to log.
        prompt_chars = sum(
            len(p.text or "")
            for c in (llm_request.contents or [])
            for p in (c.parts or [])
            if getattr(p, "text", None)
        )
        usage = genai_types.GenerateContentResponseUsageMetadata(
            prompt_token_count=max(1, prompt_chars // 4),
            candidates_token_count=max(1, len(text) // 4),
            total_token_count=max(1, prompt_chars // 4 + len(text) // 4),
        )

        yield LlmResponse(
            content=genai_types.Content(role="model", parts=[genai_types.Part(text=text)]),
            usage_metadata=usage,
            finish_reason=genai_types.FinishReason.STOP,
        )
