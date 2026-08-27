"""Extraction JSON -> TSR .docx. Deterministic, no model, no network.

This is the seam that lets extraction happen in an agent while the drafting
stays here: the agent produces the JSON described in
`references/extraction-rules.md`, and this module turns it into the firm's
document through exactly the code the CLI pipeline uses.

Everything here is validation and client resolution. The document logic lives
in `tsr_generator.api.tsr_generator_optimized.render_tsr_from_extraction`, and
there is only one copy of it.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# The contract, lifted from build_unified_prompt() in
# tsr_generator/extractors/unified_extractor.py. Documented in full in
# references/extraction-rules.md — keep the two in step.
_LAND_DETAIL_KEYS = (
    "village_name", "taluka_name", "district_name", "survey_number",
    "old_survey_number", "total_area", "nature_of_land", "owner",
)
_ENTRY_KEYS = (
    "entry_number", "date", "type", "description", "entry_status",
    "certification_status", "certification_official", "certification_date",
)

# Client fields forwarded into the report letterhead. Mirrors
# api/server.py:_build_request_metadata_for_client — an explicitly EMPTY value
# means "omit this line", so only a None (missing key) is dropped.
_CLIENT_FIELDS = (
    "client_name", "client_cin", "client_address",
    "kind_attn", "ref_prefix", "reference_email_date",
)


def _err(message: str) -> Dict[str, Any]:
    return {"success": False, "error": message}


def _validate(extraction: Any) -> Optional[str]:
    """Return a human-readable complaint about `extraction`, or None if it is
    usable. The string is shown to a lawyer in Slack, so it names the offending
    field and says what was expected."""
    if not isinstance(extraction, dict):
        return (f"extraction JSON must be a JSON object with 'land_details' and "
                f"'mutation_entries' keys, got {type(extraction).__name__}")

    if "land_details" not in extraction:
        return ("extraction JSON is missing 'land_details' (expected an object "
                "with keys like " + ", ".join(f"'{k}'" for k in _LAND_DETAIL_KEYS[:4]) + ")")
    if not isinstance(extraction["land_details"], dict):
        return (f"extraction JSON field 'land_details' must be an object, got "
                f"{type(extraction['land_details']).__name__}")

    if "mutation_entries" not in extraction:
        return ("extraction JSON is missing 'mutation_entries' (expected a list "
                "of entry objects)")
    entries = extraction["mutation_entries"]
    if not isinstance(entries, list):
        return (f"extraction JSON field 'mutation_entries' must be a list of "
                f"entry objects, got {type(entries).__name__}")
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            expected = ", ".join(f"'{k}'" for k in _ENTRY_KEYS[:4])
            return (f"extraction JSON field 'mutation_entries[{i}]' must be an "
                    f"object with keys like {expected}, got "
                    f"{type(entry).__name__}")
        if not str(entry.get("entry_number", "")).strip():
            return (f"extraction JSON field 'mutation_entries[{i}]' has no "
                    f"'entry_number' — every mutation entry needs the entry "
                    f"number it was read from")

    if "entry_numbers" in extraction and not isinstance(extraction["entry_numbers"], list):
        return (f"extraction JSON field 'entry_numbers' must be a list of entry "
                f"number strings, got {type(extraction['entry_numbers']).__name__}")

    if not entries and not (extraction.get("entry_numbers") or []):
        return ("extraction JSON has no entries at all — 'mutation_entries' and "
                "'entry_numbers' are both empty, so there is no chain of title "
                "to report")

    return None


def _resolve_client(client: Optional[str]) -> Dict[str, Any]:
    """Turn a client id into request_metadata, or explain why it cannot.

    Returns {'metadata': {...}} on success, {'error': '...'} on an unknown id.
    An id of None takes clients.json's default_client_id; an empty library
    means no client keys at all, which leaves the DOCX template's built-in
    fallback in place.
    """
    from core.clients import get_client_library

    library = get_client_library()

    if client is not None:
        if not library.clients:
            return {"error": (f"cannot use client '{client}': clients.json defines "
                              f"no clients (missing, malformed, or empty)")}
        if client not in library.clients:
            known = ", ".join(sorted(library.clients))
            return {"error": (f"unknown client id '{client}' — clients.json "
                              f"defines: {known}")}

    resolved = library.resolve(client)
    if resolved is None:
        return {"metadata": {}}

    metadata: Dict[str, str] = {}
    for field in _CLIENT_FIELDS:
        value = getattr(resolved, field)
        # "" is meaningful (omit that line); only a missing/None field falls
        # back to the built-in default.
        if value is not None:
            metadata[field] = value
    log.debug("Rendering for client %s", resolved.id)
    return {"metadata": metadata}


def render_tsr(extraction: Dict[str, Any], output_path: str,
               client: Optional[str] = None) -> Dict[str, Any]:
    """Render extraction JSON into a TSR .docx.

    Args:
        extraction: the unified-extractor JSON — see the contract in
            `references/extraction-rules.md`::

                {"land_details": {...},
                 "entry_numbers": ["3", "44", ...],
                 "mutation_entries": [{"entry_number": "44", ...}, ...]}

        output_path: where to write the .docx. Parent dirs are created.
        client: a client id from clients.json. None takes the default client.

    Returns:
        {'success': True, 'output_path', 'size_bytes', 'entries'} or
        {'success': False, 'error': '<what is wrong with the input>'}.

    Never raises for bad input: a lawyer sees the 'error' string, not a
    traceback.
    """
    problem = _validate(extraction)
    if problem:
        return _err(problem)

    if not str(output_path or "").strip():
        return _err("no output path given — pass --output <file>.docx")

    resolved = _resolve_client(client)
    if "error" in resolved:
        return _err(resolved["error"])

    from tsr_generator.api.tsr_generator_optimized import render_tsr_from_extraction

    result = render_tsr_from_extraction(
        extraction, output_path,
        request_metadata=resolved["metadata"] or None,
        logger=log,
    )
    if not result.get("success"):
        return _err(f"could not render the TSR: {result.get('error', 'unknown error')}")

    path = result["tsr_path"]
    return {
        "success": True,
        "output_path": path,
        "size_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
        "entries": result.get("entries_count", 0),
    }
