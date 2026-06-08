"""
Structured output schema for the extraction skill.

These Pydantic models mirror the JSON contract the legacy unified-extraction
prompt already asks the model to produce
(`tsr_generator.extractors.unified_extractor.build_unified_prompt`).  Using them
as the ADK ``LlmAgent.output_schema`` upgrades that contract from "please return
JSON shaped like this" to *validated, structured* output that ADK enforces via
Gemini controlled generation — while keeping the exact same field names so the
existing downstream code (`process_entry_details`, `generate_findings_table`,
`create_tsr_document`) consumes it unchanged.

Every field defaults to empty so partial / sparse extractions still validate
(land records are messy; we never want a single missing field to fail the run).
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class LandDetails(BaseModel):
    """The "Land Details" header block of a 7/12 extract."""

    village_name: str = Field(default="", description="Village name, translated to English")
    taluka_name: str = Field(default="", description="Taluka name, translated to English")
    district_name: str = Field(default="", description="District name, translated to English")
    survey_number: str = Field(default="", description="Subject survey number(s), 'Paiki/Part' -> 'p'")
    old_survey_number: str = Field(default="", description="Pre-promulgation survey number, if any")
    total_area: str = Field(default="", description="Numeric area only, e.g. '1-88-48'")
    nature_of_land: str = Field(default="", description="Tenure + use, e.g. 'New Tenure, Agricultural'")
    owner: str = Field(default="", description="Recorded owner(s)")


class MutationEntry(BaseModel):
    """One row of the chain-of-title / Entry Details table."""

    entry_number: str = Field(default="", description="Numeric entry number")
    date: str = Field(default="", description="Entry date as DD/MM/YYYY")
    type: str = Field(
        default="",
        description=(
            "One of: LOAN, DEATH, RELEASE, LOAN CLOSE, SALE, PARTITION, PERSONS ADD, "
            "TO TRANSFER, EXCHANGE, LIFETIME DISTRIBUTION, NOT RELATED, ORDER, "
            "RELINQUISHMENT, PROMULGATION"
        ),
    )
    description: str = Field(default="", description="Full English description, starts with 'That'")
    entry_status: str = Field(default="", description="certified | rejected | not_accepted")
    certification_status: str = Field(default="", description="certified | rejected | not_accepted")
    certification_official: str = Field(default="", description="Certifying officer post + place")
    certification_date: str = Field(default="", description="Certification date DD/MM/YYYY")


class UnifiedExtraction(BaseModel):
    """Top-level structured result of the extraction skill."""

    land_details: LandDetails = Field(default_factory=LandDetails)
    entry_numbers: List[str] = Field(default_factory=list)
    mutation_entries: List[MutationEntry] = Field(default_factory=list)

    def to_legacy_dicts(self) -> dict:
        """Convert to the plain-dict shapes the legacy downstream pipeline expects."""
        return {
            "land_details": self.land_details.model_dump(),
            "entry_numbers": list(self.entry_numbers),
            "mutation_entries": [e.model_dump() for e in self.mutation_entries],
        }
