"""Tests for the _build_request_metadata_for_client helper in api/server.py.

The library resolve() logic itself is exercised in test_clients_library.py;
here we focus on the server-side merging behavior.
"""

import pytest

from core.clients import Client, ClientLibrary


@pytest.fixture
def sample_library():
    abrel = Client(
        id="abrel_spv_2",
        display_name="ABREL",
        client_name="ABREL SPV 2 Limited",
        client_address="A-2, Aditya Birla Centre.",
        client_cin="(CIN: ...)",
        kind_attn="Kind Attn.: Mr. Rahul Patil",
        ref_prefix="ABREL",
        reference_email_date="21.11.2023",
    )
    other = Client(
        id="other_client",
        display_name="Other",
        client_name="Other Co",
        client_address="Somewhere else.",
    )
    return ClientLibrary(
        clients={"abrel_spv_2": abrel, "other_client": other},
        default_client_id="abrel_spv_2",
    )


def test_request_metadata_includes_resolved_client_fields(sample_library):
    """The handler logic that builds _request_metadata should merge non-None client fields."""
    from api.server import _build_request_metadata_for_client

    metadata = _build_request_metadata_for_client(
        district="Kutch",
        taluka="Abdasa",
        village="Trambo",
        survey_number="150",
        client=sample_library.resolve("abrel_spv_2"),
    )

    assert metadata["district"] == "Kutch"
    assert metadata["client_name"] == "ABREL SPV 2 Limited"
    assert metadata["ref_prefix"] == "ABREL"
    assert metadata["kind_attn"] == "Kind Attn.: Mr. Rahul Patil"


def test_request_metadata_skips_none_client_fields(sample_library):
    """Optional client fields that are None should not be added to request_metadata."""
    from api.server import _build_request_metadata_for_client

    metadata = _build_request_metadata_for_client(
        district="Kutch",
        taluka="Abdasa",
        village="Trambo",
        survey_number="150",
        client=sample_library.resolve("other_client"),  # has only required fields
    )

    assert metadata["client_name"] == "Other Co"
    assert "client_cin" not in metadata
    assert "kind_attn" not in metadata
    assert "ref_prefix" not in metadata


def test_request_metadata_no_client_passes_geography_only():
    """When client is None (empty library), only geography is in request_metadata."""
    from api.server import _build_request_metadata_for_client

    metadata = _build_request_metadata_for_client(
        district="Kutch",
        taluka="Abdasa",
        village="Trambo",
        survey_number="150",
        client=None,
    )

    assert metadata == {
        "district": "Kutch",
        "taluka": "Abdasa",
        "village": "Trambo",
        "survey_number": "150",
    }


def test_unknown_client_id_falls_back_to_default_via_metadata(sample_library):
    """When client_id is unknown, library resolves to default and metadata gets default fields."""
    from api.server import _build_request_metadata_for_client

    resolved = sample_library.resolve("does-not-exist")
    metadata = _build_request_metadata_for_client(
        district="Kutch",
        taluka="Abdasa",
        village="Trambo",
        survey_number="150",
        client=resolved,
    )

    # Default client (abrel_spv_2) fields should be present
    assert metadata["client_name"] == "ABREL SPV 2 Limited"
    assert metadata["ref_prefix"] == "ABREL"
