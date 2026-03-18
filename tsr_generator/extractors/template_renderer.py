"""
Deterministic template renderer for structured entry descriptions.

Takes structured fields extracted by the LLM and assembles canonical
description strings for each entry type. No LLM calls -- pure string
assembly with graceful omission of missing optional clauses.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _join_names(names: Optional[List[str]]) -> str:
    """Join a list of names with ', '. Returns '' if empty/None."""
    if not names:
        return ""
    return ", ".join(n for n in names if n)


def _survey_str(survey_numbers: Optional[List[str]]) -> str:
    """Format survey numbers with 'Survey No.' prefix."""
    if not survey_numbers:
        return ""
    return "Survey No. " + ", ".join(s for s in survey_numbers if s)


def _amount_str(amount: Optional[str]) -> str:
    """Wrap an amount with 'Rs. ' prefix and '/-' suffix."""
    if not amount:
        return ""
    return f"Rs. {amount}/-"


def _has_any(fields: Dict[str, Any], keys: List[str]) -> bool:
    """Return True if at least one key has a non-empty value."""
    for k in keys:
        v = fields.get(k)
        if v is None:
            continue
        if isinstance(v, (list, dict)) and len(v) == 0:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return True
    return False


def _log_omitted(entry_type: str, fields: Dict[str, Any], all_keys: List[str]) -> None:
    """Log fields that are missing/empty at DEBUG level."""
    for k in all_keys:
        v = fields.get(k)
        is_empty = (
            v is None
            or (isinstance(v, str) and v.strip() == "")
            or (isinstance(v, (list, dict)) and len(v) == 0)
        )
        if is_empty:
            logger.debug("Omitted field '%s' for entry type %s", k, entry_type)


# ---------------------------------------------------------------------------
# Per-type renderer functions
# ---------------------------------------------------------------------------


def _render_sale(fields: Dict[str, Any]) -> str:
    type_keys = ["sellers", "buyers", "survey_numbers", "area",
                 "consideration_amount", "document_number", "document_date"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("SALE", fields, type_keys)

    sellers = _join_names(fields.get("sellers"))
    buyers = _join_names(fields.get("buyers"))
    surveys = _survey_str(fields.get("survey_numbers"))
    area = fields.get("area", "") or ""
    amount = fields.get("consideration_amount", "") or ""
    doc_num = fields.get("document_number", "") or ""
    doc_date = fields.get("document_date", "") or ""

    parts = [f"That {sellers} sold land"]
    if surveys:
        parts.append(f"bearing {surveys}")
    if area:
        parts.append(f"measuring {area}")
    if buyers:
        parts.append(f"to {buyers}")
    if doc_num and doc_date:
        parts.append(f"through document no. {doc_num} dated {doc_date}")
    elif doc_num:
        parts.append(f"through document no. {doc_num}")
    elif doc_date:
        parts.append(f"dated {doc_date}")
    if amount:
        parts.append(f"in consideration of {_amount_str(amount)}")

    return " ".join(parts) + "."


def _render_inheritance(fields: Dict[str, Any]) -> str:
    type_keys = ["deceased", "heirs", "survey_numbers", "area"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("INHERITANCE", fields, type_keys)

    deceased = fields.get("deceased", "") or ""
    heirs = _join_names(fields.get("heirs"))
    surveys = _survey_str(fields.get("survey_numbers"))
    area = fields.get("area", "") or ""

    parts = [f"That upon the demise of {deceased}"]
    land = "the land"
    if surveys:
        land = f"the land bearing {surveys}"
    if area:
        land += f" measuring {area}"
    parts.append(f"{land} came to be mutated in the names of legal heirs: {heirs}.")

    return ", ".join(parts[:1]) + ", " + parts[1] if len(parts) > 1 else parts[0]


def _render_partition(fields: Dict[str, Any]) -> str:
    type_keys = ["original_owner", "recipients", "survey_numbers", "area", "allocations"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("PARTITION", fields, type_keys)

    owner = fields.get("original_owner", "") or ""
    allocations = fields.get("allocations") or []

    parts = [f"That {owner} distributed the land as follows:"]

    if allocations:
        alloc_lines = []
        for i, alloc in enumerate(allocations, 1):
            name = alloc.get("name", "")
            sn = alloc.get("survey_number", "")
            ar = alloc.get("area", "")
            line_parts = [name]
            if sn:
                line_parts.append(f"Survey No. {sn}")
            if ar:
                line_parts.append(ar)
            alloc_lines.append(f"{i}. " + " - ".join(line_parts))
        parts.append("\n".join(alloc_lines))
    parts.append(
        "The partition was recorded based on application and consent "
        "as per respective rights and physical possession."
    )
    return " ".join(parts)


def _render_relinquishment(fields: Dict[str, Any]) -> str:
    type_keys = ["relinquisher", "beneficiaries", "survey_numbers", "area", "relationship"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("RELINQUISHMENT", fields, type_keys)

    relinquisher = fields.get("relinquisher", "") or ""
    beneficiaries = _join_names(fields.get("beneficiaries"))
    surveys = _survey_str(fields.get("survey_numbers"))
    area = fields.get("area", "") or ""

    parts = [f"That {relinquisher} relinquished their share"]
    if surveys:
        parts.append(f"in land bearing {surveys}")
        if area:
            parts.append(f"measuring {area}")
    if beneficiaries:
        parts.append(f"in favour of {beneficiaries}")

    return " ".join(parts) + "."


def _render_exchange(fields: Dict[str, Any]) -> str:
    type_keys = ["party_a", "party_b", "survey_a", "survey_b", "area_a", "area_b"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("EXCHANGE", fields, type_keys)

    party_a = _join_names(fields.get("party_a"))
    party_b = _join_names(fields.get("party_b"))
    survey_a = _survey_str(fields.get("survey_a"))
    survey_b = _survey_str(fields.get("survey_b"))
    area_a = fields.get("area_a", "") or ""
    area_b = fields.get("area_b", "") or ""

    parts = [f"That {party_a} and {party_b} exchanged their lands."]
    transfer = f"{party_a} transferred {survey_a}"
    if area_a:
        transfer += f" measuring {area_a}"
    transfer += f" and received {survey_b}"
    if area_b:
        transfer += f" measuring {area_b}"
    transfer += "."
    parts.append(transfer)

    return " ".join(parts)


def _render_lifetime_distribution(fields: Dict[str, Any]) -> str:
    type_keys = ["distributor", "recipients", "survey_numbers", "area", "allocations"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("LIFETIME_DISTRIBUTION", fields, type_keys)

    distributor = fields.get("distributor", "") or ""
    allocations = fields.get("allocations") or []

    parts = [f"That {distributor} distributed the land during their lifetime as follows:"]

    if allocations:
        alloc_lines = []
        for i, alloc in enumerate(allocations, 1):
            name = alloc.get("name", "")
            sn = alloc.get("survey_number", "")
            ar = alloc.get("area", "")
            line_parts = [name]
            if sn:
                line_parts.append(f"Survey No. {sn}")
            if ar:
                line_parts.append(ar)
            alloc_lines.append(f"{i}. " + " - ".join(line_parts))
        parts.append("\n".join(alloc_lines))

    return " ".join(parts)


def _render_gift(fields: Dict[str, Any]) -> str:
    type_keys = ["donor", "recipients", "survey_numbers", "area",
                 "document_number", "document_date"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("GIFT", fields, type_keys)

    donor = fields.get("donor", "") or ""
    recipients = _join_names(fields.get("recipients"))
    surveys = _survey_str(fields.get("survey_numbers"))
    area = fields.get("area", "") or ""
    doc_num = fields.get("document_number", "") or ""
    doc_date = fields.get("document_date", "") or ""

    parts = [f"That {donor} gifted land"]
    if surveys:
        parts.append(f"bearing {surveys}")
    if area:
        parts.append(f"measuring {area}")
    if recipients:
        parts.append(f"to {recipients}")
    if doc_num and doc_date:
        parts.append(f"through document no. {doc_num} dated {doc_date}")
    elif doc_num:
        parts.append(f"through document no. {doc_num}")

    return " ".join(parts) + "."


def _render_loan(fields: Dict[str, Any]) -> str:
    type_keys = ["borrowers", "lender", "survey_numbers", "amount"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("LOAN", fields, type_keys)

    borrowers = _join_names(fields.get("borrowers"))
    lender = fields.get("lender", "") or ""
    surveys = _survey_str(fields.get("survey_numbers"))
    amount = fields.get("amount", "") or ""

    parts = [f"That {borrowers} created a charge on land"]
    if surveys:
        parts.append(f"bearing {surveys}")
    if lender:
        parts.append(f"by taking loan from {lender}")
    if amount:
        parts.append(f"for a sum of {_amount_str(amount)}")

    result = " ".join(parts) + "."
    if lender:
        result += (
            f" Therefore a charge in favour of {lender} was registered "
            "in the revenue records."
        )
    return result


def _render_release(fields: Dict[str, Any]) -> str:
    type_keys = ["applicants", "lender", "survey_numbers", "reference_entry_number"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("RELEASE", fields, type_keys)

    applicants = _join_names(fields.get("applicants"))
    lender = fields.get("lender", "") or ""
    ref = fields.get("reference_entry_number", "") or ""

    lender_clause = ""
    if lender and ref:
        lender_clause = f" of {lender} (Entry No. {ref})"
    elif lender:
        lender_clause = f" of {lender}"
    elif ref:
        lender_clause = f" (Entry No. {ref})"

    return (
        f"That upon receiving an application from {applicants} for exemption "
        f"of burden{lender_clause}, the said exemption of burden has been recorded."
    )


def _render_seizure(fields: Dict[str, Any]) -> str:
    type_keys = ["bank", "survey_numbers", "borrowers", "reference_entry_number"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("SEIZURE", fields, type_keys)

    bank = fields.get("bank", "") or ""
    surveys = _survey_str(fields.get("survey_numbers"))
    borrowers = _join_names(fields.get("borrowers"))
    ref = fields.get("reference_entry_number", "") or ""

    parts = [f"That {bank} seized the land"]
    if surveys:
        parts.append(f"bearing {surveys}")
    if borrowers:
        parts.append(f"of {borrowers}")
    if ref:
        parts.append(f"under the charge created in Entry No. {ref}")

    return " ".join(parts) + "."


def _render_order(fields: Dict[str, Any]) -> str:
    type_keys = ["authority", "order_number", "order_date", "survey_numbers",
                 "affected_parties", "order_summary"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("ORDER", fields, type_keys)

    authority = fields.get("authority", "") or ""
    order_num = fields.get("order_number", "") or ""
    order_date = fields.get("order_date", "") or ""
    summary = fields.get("order_summary", "") or ""

    parts = [f"That {authority}"]
    if order_num and order_date:
        parts.append(f"vide Order No. {order_num} dated {order_date}")
    elif order_num:
        parts.append(f"vide Order No. {order_num}")
    elif order_date:
        parts.append(f"vide order dated {order_date}")
    if summary:
        parts.append(f"ordered {summary}")

    return " ".join(parts) + "."


def _render_allotment(fields: Dict[str, Any]) -> str:
    type_keys = ["grantee", "survey_numbers", "area", "authority", "legal_basis"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("ALLOTMENT", fields, type_keys)

    grantee = _join_names(fields.get("grantee"))
    surveys = _survey_str(fields.get("survey_numbers"))
    area = fields.get("area", "") or ""
    authority = fields.get("authority", "") or ""
    legal_basis = fields.get("legal_basis", "") or ""

    parts = [f"That {grantee} was granted land"]
    if surveys:
        parts.append(f"bearing {surveys}")
    if area:
        parts.append(f"measuring {area}")
    if authority:
        parts.append(f"by {authority}")
    if legal_basis:
        parts.append(f"under {legal_basis}")

    return " ".join(parts) + "."


def _render_tenure_change(fields: Dict[str, Any]) -> str:
    type_keys = ["authority", "order_number", "order_date", "survey_numbers",
                 "from_tenure", "to_tenure"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("TENURE_CHANGE", fields, type_keys)

    authority = fields.get("authority", "") or ""
    order_num = fields.get("order_number", "") or ""
    order_date = fields.get("order_date", "") or ""
    from_tenure = fields.get("from_tenure", "") or ""
    to_tenure = fields.get("to_tenure", "") or ""

    parts = [f"That {authority}"]
    if order_num and order_date:
        parts.append(f"vide Order No. {order_num} dated {order_date}")
    elif order_num:
        parts.append(f"vide Order No. {order_num}")
    if from_tenure and to_tenure:
        parts.append(f"changed the condition of the land from {from_tenure} to {to_tenure}")
    elif to_tenure:
        parts.append(f"changed the condition of the land to {to_tenure}")

    result = " ".join(parts) + "."
    if from_tenure:
        result += f" The aforesaid land is free from the restrictions of {from_tenure}."
    return result


def _render_land_acquisition(fields: Dict[str, Any]) -> str:
    type_keys = ["authority", "award_number", "award_date", "survey_numbers",
                 "areas", "purpose"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("LAND_ACQUISITION", fields, type_keys)

    authority = fields.get("authority", "") or ""
    award_num = fields.get("award_number", "") or ""
    award_date = fields.get("award_date", "") or ""
    surveys = _survey_str(fields.get("survey_numbers"))
    purpose = fields.get("purpose", "") or ""

    parts = [f"That {authority}"]
    if award_num and award_date:
        parts.append(f"vide Award No. {award_num} dated {award_date}")
    elif award_num:
        parts.append(f"vide Award No. {award_num}")
    land = "acquired land"
    if surveys:
        land += f" bearing {surveys}"
    parts.append(land)
    if purpose:
        parts.append(f"for {purpose}")

    return " ".join(parts) + "."


def _render_lease(fields: Dict[str, Any]) -> str:
    type_keys = ["lessor", "lessee", "survey_numbers", "area", "period", "purpose"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("LEASE", fields, type_keys)

    lessor = _join_names(fields.get("lessor"))
    lessee = fields.get("lessee", "") or ""
    surveys = _survey_str(fields.get("survey_numbers"))
    area = fields.get("area", "") or ""
    period = fields.get("period", "") or ""
    purpose = fields.get("purpose", "") or ""

    parts = [f"That {lessor} leased land"]
    if surveys:
        parts.append(f"bearing {surveys}")
    if area:
        parts.append(f"measuring {area}")
    if lessee:
        parts.append(f"to {lessee}")
    if period:
        parts.append(f"for a period of {period}")
    if purpose:
        parts.append(f"for {purpose}")

    return " ".join(parts) + "."


def _render_promulgation(fields: Dict[str, Any]) -> str:
    type_keys = ["authority", "survey_number_mapping", "effective_date"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("PROMULGATION", fields, type_keys)

    authority = fields.get("authority", "") or ""
    mapping = fields.get("survey_number_mapping") or {}
    eff_date = fields.get("effective_date", "") or ""

    parts = [f"That upon re-survey by {authority}, new survey numbers were assigned."]

    if mapping:
        for old_sn, new_sns in mapping.items():
            new_str = ", ".join(new_sns) if isinstance(new_sns, list) else str(new_sns)
            parts.append(
                f"Old Survey No. {old_sn} became new Survey No. {new_str}."
            )
    if eff_date:
        parts.append(f"Effective date: {eff_date}.")

    return " ".join(parts)


def _render_correction(fields: Dict[str, Any]) -> str:
    type_keys = ["correction_type", "original_value", "corrected_value",
                 "reference_entry_number"]
    if not _has_any(fields, type_keys):
        return ""
    _log_omitted("CORRECTION", fields, type_keys)

    corr_type = fields.get("correction_type", "") or ""
    original = fields.get("original_value", "") or ""
    corrected = fields.get("corrected_value", "") or ""
    ref = fields.get("reference_entry_number", "") or ""

    parts = [f"That {corr_type} was corrected"]
    if original and corrected:
        parts.append(f"from '{original}' to '{corrected}'")
    elif corrected:
        parts.append(f"to '{corrected}'")
    if ref:
        parts.append(f"in Entry No. {ref}")

    return " ".join(parts) + "."


def _render_not_related(_fields: Dict[str, Any]) -> str:
    return "This entry is not related to the present survey number(s)."


def _render_unavailable(_fields: Dict[str, Any]) -> str:
    return "The data for this entry is not available."


# ---------------------------------------------------------------------------
# Renderer registry
# ---------------------------------------------------------------------------

RENDERERS: Dict[str, Callable[[Dict[str, Any]], str]] = {
    "SALE": _render_sale,
    "INHERITANCE": _render_inheritance,
    "PARTITION": _render_partition,
    "RELINQUISHMENT": _render_relinquishment,
    "EXCHANGE": _render_exchange,
    "LIFETIME_DISTRIBUTION": _render_lifetime_distribution,
    "GIFT": _render_gift,
    "LOAN": _render_loan,
    "RELEASE": _render_release,
    "SEIZURE": _render_seizure,
    "ORDER": _render_order,
    "ALLOTMENT": _render_allotment,
    "TENURE_CHANGE": _render_tenure_change,
    "LAND_ACQUISITION": _render_land_acquisition,
    "LEASE": _render_lease,
    "PROMULGATION": _render_promulgation,
    "CORRECTION": _render_correction,
    "NOT_RELATED": _render_not_related,
    "UNAVAILABLE": _render_unavailable,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_entry_description(entry_type: str, fields: Dict[str, Any]) -> str:
    """
    Render a description string for an entry using its type and structured fields.

    Args:
        entry_type: Canonical type string (e.g., "SALE", "LOAN")
        fields: Dict of extracted structured fields

    Returns:
        Assembled description string. Empty string if no type-specific fields
        populated or if the entry type is unknown.
    """
    renderer = RENDERERS.get(entry_type)
    if renderer is None:
        logger.debug("No renderer registered for entry type '%s'", entry_type)
        return ""
    return renderer(fields)
