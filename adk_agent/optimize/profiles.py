"""
Prompt *profiles* — the tunable surface the optimizer searches over.

A :class:`PromptProfile` is a named bundle of efficiency levers:

  * **Static prompt blocks** (``entry_type_rules``, ``formatting_rules``,
    ``description_examples``, ``certification_patterns``) — each ``"full"``,
    ``"compact"`` or ``"off"``. These blocks are re-sent on *every* extraction
    call and dominate the fixed prompt cost (``description_examples`` alone is
    ~3.5 KB), so compacting them is the biggest token lever.
  * **Section pruning** (``prune_threshold``) — trim a long land record down to
    its land-details header + entry-details section above N characters.
  * **Decoding / model** (``model_name``, ``temperature``, ``thinking_budget``,
    ``max_output_tokens``) — route to a cheaper model or cap thinking/output.

The canonical :data:`FULL_PROFILE` (all blocks ``"full"``, default pruning, no
overrides) is the **baseline**: :func:`build_prompt` detects it and delegates to
the production :func:`build_extraction_prompt`, so the baseline prompt is
byte-for-byte identical to what ships today. Every other profile is a candidate
the regression gate must justify.

Reuses the exact production prompt constants (imported, never copied) so a
"full" block is literally the shipping text.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Production prompt constants + builder (reused, never duplicated).
from tsr_generator.extractors.unified_extractor import (
    CLASSIFY_NOT_RELATED_ENTRIES,
    ENTRY_TYPE_RULES,
    FORMATTING_RULES,
    DESCRIPTION_EXAMPLES,
    CERTIFICATION_PATTERNS,
    _identify_entry_numbers_fast,
)
from adk_agent.skills.extraction import build_extraction_prompt, inject_guidelines

# The default section-prune threshold matches the production
# ``_extract_relevant_sections`` (which only trims documents longer than this).
DEFAULT_PRUNE_THRESHOLD = 15000

# Candidate cheaper/faster models to route extraction to (verified available).
FLASH_MODEL = "gemini-3.5-flash"        # ~25% cheaper, ~4x faster than 3.1-pro
FLASH_LITE_MODEL = "gemini-3.1-flash-lite"

# USD per 1M tokens (input, output). 3.1-pro ($2/$12) and 3.5-flash ($1.5/$9)
# are published list prices; flash-lite is an approximate lower tier (used only
# for *relative* cost ranking in the optimizer, not billing).
MODEL_PRICING = {
    "gemini-3.1-pro-preview": (2.0, 12.0),
    "gemini-3-pro-preview": (2.0, 12.0),
    "gemini-pro-latest": (2.0, 12.0),
    "gemini-3.5-flash": (1.5, 9.0),
    "gemini-3-flash-preview": (1.5, 9.0),
    "gemini-flash-latest": (1.5, 9.0),
    "gemini-3.1-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite-preview": (0.30, 2.50),
}
_DEFAULT_PRICING = (2.0, 12.0)


def estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated USD cost of a call (strips the offline ``fake-`` prefix)."""
    name = (model_name or "").replace("fake-", "")
    inp, out = MODEL_PRICING.get(name, _DEFAULT_PRICING)
    return input_tokens / 1e6 * inp + output_tokens / 1e6 * out


# --------------------------------------------------------------------------- #
# Compact variants of the heavy static blocks.
#
# These preserve every *rule* but strip the worked "wrong example" commentary
# and redundant phrasing. They are candidates — the gate decides whether they
# hold accuracy. (On real data with golden truth, a compact block that loses a
# nuance shows up as a field/type accuracy drop and is rejected.)
# --------------------------------------------------------------------------- #

ENTRY_TYPE_RULES_COMPACT = ENTRY_TYPE_RULES  # already terse (~12 lines)

FORMATTING_RULES_COMPACT = """
Formatting Rules:
1. Descriptions start with "That" (except NOT RELATED, PROMULGATION).
2. No honorifics (Shri/Smt/Mr./Mrs.) and no "account holder" / "mortgaged his total land" / "of [village] village".
3. LOAN/RELEASE: no "based on the agreement dated...". INHERITANCE/DEATH and PARTITION/LIFETIME DISTRIBUTION: include a closing sentence listing the supporting documents.
4. Direct and factual; keep all legally relevant detail, no commentary.
5. Amounts "Rs. X/-"; documents "document no. X dated DD/MM/YYYY"; always 4-digit years.
6. Survey numbers: use "Survey No." (not Khata/Account No.); translate Paiki/Part/pk -> "p" and preserve "/" (e.g. "387/p3"); append Khata in parentheses when shown (e.g. "193p1(28)").
7. Caste titles only when part of the name (Thakor, Patel, Kanbi, Choudhary, Rabari, Vadher, Solanki); "ben" suffix -> "ben".
8. total_area field: numeric only (e.g. "1-88-48"); in descriptions use "Acre/Guntha" or "Hectare".
9. Lists: "which are as follows:-" then names on separate lines.
10. OLD SURVEY NUMBERS: if a PROMULGATION (re-survey) entry exists, use "old Survey No." for entries BEFORE it and "Survey No." after; otherwise "Survey No.".
11. "Prant Officer"/"પ્રાંત અધિકારી" -> "Province Officer"/"Province court".
12. Borewells: always "Borewell-1", "Borewell-2" (drop "pucca"; never "Bore-1").
"""

DESCRIPTION_EXAMPLES_COMPACT = """
Description patterns (one canonical example per type):

AREA RULE: For every type EXCEPT LOAN and RELEASE, when the source states an area, include it as "measuring <area> Hectare" (or Acre/Guntha) right after the Survey No. clause; convert Gujarati numerals, keep dash format (e.g. "6-21-20"). LOAN/RELEASE: never include area.

- LOAN: "That [Borrower] took a loan of Rs. X/- on land bearing Survey No. A(khata), B(khata) from [Bank], [Branch]." Include ALL surveys from the બોજા/Other-Rights column (with khata in parentheses), in source order; no area, no agreement date.
- RELEASE: "That upon receiving an application from [Name] for removing the charge of [Bank], [Branch]. The said exemption of burden has been recorded. Entry No. X."
- SALE: "That [Seller] sold Survey No. X measuring <area> Hectare to [Buyer] for Rs. X/- vide document no. Y dated DD/MM/YYYY."
- DEATH/INHERITANCE: "That upon the demise of [Name] on DD/MM/YYYY (death certificate no. [X]), his/her share in land bearing old Survey No. X measuring <area> Hectare came to be mutated in the names of his/her legal heirs which are as follows:-\\n[Heir] - [relationship] - age [N]\\n...\\nThis inheritance was recorded based on the application, death certificate, genealogy (Pedhinamu) and affidavits." Omit any segment the source lacks; never invent.
- PARTITION: lead-in "That the said [Owners] distributed their land bearing Survey No. X measuring <area> Hectare among themselves as follows:-" then one bare row per recipient ("[Name] - Survey No. [X] - [area]"), blank line, then "The distribution/Partition ... recorded based on their application and their consent ...". Allocation rows are mandatory when shown; no "1.", "2." prefixes.
- LIFETIME_DISTRIBUTION/PERSONS_ADD/TO_TRANSFER: "That the said [Distributor] made an application of life time distribution in his land bearing Survey No. X measuring <area> Hectare to his legal heirs which are as follows:-" then bare beneficiary rows. Single beneficiary stays one sentence.
- ORDER (allotment): "That Government survey was conducted and land bearing Survey No. X measuring <area> Hectare was allotted to [Name]." (circular): "That as per Taluka Circular No. X dated Y, Survey No. Z measuring <area> Hectare allotted to [Name]." (correction): list ALL surveys/corrections exactly as in the order.
- NOT RELATED: "This Entry is not related to Present Survey Number."
- PROMULGATION: extract the FULL procedural text (authority, court, order numbers+dates, notice/objection period, Mamlatdar preparation, Province verification, finalization, page/survey range); preserve old/new area pairs verbatim. Do not summarize.
"""

CERTIFICATION_PATTERNS_COMPACT = """
Certification (read the "Remarks of the Inspecting Officer" column, incl. Gujarati):
- રદ -> "rejected" ("The Entry is cancelled by [Name] on DD/MM/YYYY.")
- ના મંજૂર / નામંજુર / નામંજૂર -> "not_accepted"/"rejected" ("The Entry is not accepted by ...")
- પ્રમાણિત -> "certified" ("The Entry is certified by ...")
- Never output "certified" if રદ/ના મંજૂર/નામંજુર is present. Default unclear -> "".
- certification_official = officer POST/DESIGNATION + PLACE (e.g. "C.O. Porbandar"), no personal names.
- certification_official and certification_date are REQUIRED when visible; 4-digit year dates.
"""

# Block registry: name -> {variant -> text}. "off" omits the block entirely.
_BLOCKS: Dict[str, Dict[str, str]] = {
    "entry_type_rules": {"full": ENTRY_TYPE_RULES, "compact": ENTRY_TYPE_RULES_COMPACT, "off": ""},
    "formatting_rules": {"full": FORMATTING_RULES, "compact": FORMATTING_RULES_COMPACT, "off": ""},
    "description_examples": {"full": DESCRIPTION_EXAMPLES, "compact": DESCRIPTION_EXAMPLES_COMPACT, "off": ""},
    "certification_patterns": {"full": CERTIFICATION_PATTERNS, "compact": CERTIFICATION_PATTERNS_COMPACT, "off": ""},
}
_BLOCK_NAMES = tuple(_BLOCKS.keys())
_VARIANTS = ("full", "compact", "off")


@dataclass
class PromptProfile:
    """A named bundle of extraction efficiency levers."""

    name: str = "full"
    description: str = ""

    # Static prompt blocks: "full" | "compact" | "off".
    entry_type_rules: str = "full"
    formatting_rules: str = "full"
    description_examples: str = "full"
    certification_patterns: str = "full"

    # Section pruning: trim documents longer than this (chars) to relevant sections.
    prune_threshold: int = DEFAULT_PRUNE_THRESHOLD

    # Decoding / model levers (effective on live runs; offline they are inert).
    model_name: Optional[str] = None          # None -> config default
    temperature: float = 0.0
    thinking_budget: Optional[int] = None     # None -> inherit; 0 -> disable; >0 -> cap
    max_output_tokens: Optional[int] = None

    # Deterministic entity-map grounding pre-pass (zero LLM cost): injects a
    # "VERIFIED ENTITIES" block so a cheaper model holds accuracy on survey/khata.
    entity_map: bool = False

    # ------------------------------------------------------------------ helpers
    def block_variant(self, block: str) -> str:
        return getattr(self, block)

    def with_levers(self, name: str, **changes) -> "PromptProfile":
        """Return a copy with *changes* applied and a new name."""
        return replace(self, name=name, **changes)

    def is_canonical_full(self) -> bool:
        """True iff this profile reproduces the shipping production prompt exactly."""
        return (
            all(self.block_variant(b) == "full" for b in _BLOCK_NAMES)
            and self.prune_threshold == DEFAULT_PRUNE_THRESHOLD
            and self.model_name is None
            and self.temperature == 0.0
            and self.thinking_budget is None
            and self.max_output_tokens is None
            and not self.entity_map
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PromptProfile":
        fields = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (d or {}).items() if k in fields})


FULL_PROFILE = PromptProfile(
    name="full",
    description="Baseline — the current production extraction prompt, unchanged.",
)


def _prune_sections(pdf_text: str, threshold: int) -> str:
    """
    Parameterized variant of the production ``_extract_relevant_sections``.

    Documents at or under *threshold* chars pass through unchanged; longer ones
    are trimmed to the land-details header + the Entry Details section.
    """
    text = pdf_text or ""
    if len(text) <= threshold:
        return text
    sections = [text[:3500]]
    m = re.search(r"Entry Details", text, re.IGNORECASE)
    if m:
        end = re.search(r"Jantri Detail", text[m.start():], re.IGNORECASE)
        end_pos = m.start() + end.start() + 500 if end else min(m.start() + 12000, len(text))
        section = text[m.start():end_pos]
        if section not in sections[0]:
            sections.append(section)
    return "\n\n[...]\n\n".join(sections)


def _compose_unified_prompt(
    document_text: str, hints: List[str], profile: PromptProfile, grounding: str = ""
) -> str:
    """
    Compose the unified extraction prompt with the profile's block variants.

    Mirrors the structure of the production ``build_unified_prompt`` but swaps in
    compact / omitted blocks (and an optional deterministic *grounding* block).
    Used only for non-canonical profiles; the canonical ``full`` profile delegates
    to the production builder for exact parity.
    """
    grounding_block = ("\n" + grounding.strip() + "\n") if grounding else ""
    entry_hint_text = ""
    if hints:
        entry_hint_text = f"\nCandidate entry numbers detected: {', '.join(hints)}"

    not_related_instruction = ""
    if CLASSIFY_NOT_RELATED_ENTRIES:
        not_related_instruction = (
            '\nNOT RELATED ENTRIES: If an entry clearly pertains to survey numbers '
            "different from the subject survey number being investigated, classify it as "
            'NOT RELATED with description: "This Entry is not related to Present Survey Number."\n'
        )

    def block(name: str) -> str:
        return _BLOCKS[name][profile.block_variant(name)]

    return f"""Extract ALL information from this Gujarat land record in ONE response.

OUTPUT FORMAT - Return ONLY valid JSON with this exact structure:
{{
  "land_details": {{
    "village_name": "",
    "taluka_name": "",
    "district_name": "",
    "survey_number": "",
    "old_survey_number": "",
    "total_area": "",
    "nature_of_land": "",
    "owner": ""
  }},
  "entry_numbers": [],
  "mutation_entries": [
    {{
      "entry_number": "",
      "date": "",
      "type": "",
      "description": "",
      "entry_status": "",
      "certification_status": "",
      "certification_official": "",
      "certification_date": ""
    }}
  ]
}}

EXTRACTION INSTRUCTIONS:

1. LAND DETAILS: Extract from the "Land Details" section. Translate ALL Gujarati to English.
   - For "nature_of_land", include BOTH tenure (Old/New) and use (Agricultural/Non-Agri), separated by comma.
   - For "survey_number", translate "Paiki" or "Part" or "part" to "p"(e.g. "150/p1").
   - For "old_survey_number", look for re-survey promulgation entries that map old->new survey numbers.

2. ENTRY NUMBERS: Extract from "Entry Details" table. Output as array of number strings.
   - Remove asterisks (*) and trailing Gujarati text; only actual entry numbers.
{entry_hint_text}

3. MUTATION ENTRIES: For each entry number, extract entry_number, date (DD/MM/YYYY),
   type (LOAN, DEATH, RELEASE, LOAN CLOSE, SALE, PARTITION, PERSONS ADD, TO TRANSFER,
   EXCHANGE, LIFETIME DISTRIBUTION, NOT RELATED, ORDER, RELINQUISHMENT, PROMULGATION),
   description (IN ENGLISH, translate all Gujarati), entry_status / certification_status
   ("certified"/"rejected"/"not_accepted"/""), certification_official, certification_date.
{block('entry_type_rules')}
{block('formatting_rules')}
{block('description_examples')}
{block('certification_patterns')}
{not_related_instruction}
For entries with only a number in the table (no details), include with empty fields.
For entries where content is not legible, set description to:
"Entry mentioned in the document but content is not legible."
{grounding_block}
DOCUMENT TEXT:
{document_text}

Return ONLY the JSON object, no explanations."""


def build_prompt(pdf_text: str, guidelines_text: str, profile: Optional[PromptProfile] = None) -> str:
    """
    Render the extraction prompt for *profile*.

    The canonical ``full`` profile delegates to the production builder (exact
    baseline parity); any other profile is composed from the parameterized
    blocks + section pruning, then has learned guidelines injected.
    """
    profile = profile or FULL_PROFILE
    if profile.is_canonical_full():
        return build_extraction_prompt(pdf_text, guidelines_text)

    document_text = _prune_sections(pdf_text or "", profile.prune_threshold)
    hints = _identify_entry_numbers_fast(pdf_text or "")
    grounding = ""
    if profile.entity_map:
        # Lazy import: the deterministic grounding "tool" pulls in tsr_generator regex.
        from adk_agent.skills.entity_map import entity_map_block

        grounding = entity_map_block(pdf_text or "")
    prompt = _compose_unified_prompt(document_text, hints, profile, grounding=grounding)
    return inject_guidelines(prompt, guidelines_text)


# --------------------------------------------------------------------------- #
# Search space — single-lever mutations applied greedily by the loop.
# --------------------------------------------------------------------------- #

def lever_candidates() -> List[Tuple[str, Dict[str, Any]]]:
    """
    The ordered set of efficiency levers the loop tries (greedily compounding the
    accepted ones). Each entry is ``(lever_name, profile_field_changes)``.
    """
    return [
        # Prompt compaction — fewer fixed tokens per call (proven offline + online).
        ("compact_description_examples", {"description_examples": "compact"}),
        ("compact_formatting_rules", {"formatting_rules": "compact"}),
        ("compact_certification_patterns", {"certification_patterns": "compact"}),
        ("compact_entry_type_rules", {"entry_type_rules": "compact"}),
        ("prune_8k", {"prune_threshold": 8000}),
        ("prune_6k", {"prune_threshold": 6000}),
        # Model routing — the big cost/latency lever. Flash is ~25% cheaper and
        # ~4x faster; deterministic entity-map grounding is bundled so the smaller
        # model holds accuracy on survey/khata (the gate validates the pairing).
        ("route_flash_with_grounding", {"model_name": FLASH_MODEL, "entity_map": True}),
        ("route_flash", {"model_name": FLASH_MODEL}),
        ("route_flash_lite_with_grounding", {"model_name": FLASH_LITE_MODEL, "entity_map": True}),
        ("thinking_off", {"thinking_budget": 0}),
    ]


# --------------------------------------------------------------------------- #
# Active-profile persistence — the promoted winner every run reads.
# --------------------------------------------------------------------------- #

def save_active_profile(path: Path, profile: PromptProfile) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_active_profile(path: Path) -> Optional[PromptProfile]:
    """Load the promoted profile, or ``None`` if none has been promoted."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        return PromptProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None
