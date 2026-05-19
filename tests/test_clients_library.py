"""Tests for the clients library loader."""

import json
import pytest
from pathlib import Path

from core.clients import (
    Client,
    ClientLibrary,
    load_client_library,
    get_client_library,
)


def _write_clients_file(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "clients.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_loads_valid_library(tmp_path):
    path = _write_clients_file(tmp_path, {
        "default_client_id": "abrel_spv_2",
        "clients": [
            {
                "id": "abrel_spv_2",
                "display_name": "ABREL SPV 2 Limited",
                "client_name": "ABREL SPV 2 Limited",
                "client_cin": "(CIN: U40108MH2020PLC352631),",
                "client_address": "A-2, Aditya Birla Centre,\nWorli, Mumbai-400030.",
                "kind_attn": "Kind Attn.: Mr. Rahul Patil",
                "ref_prefix": "ABREL",
                "reference_email_date": "21.11.2023",
            }
        ],
    })

    lib = load_client_library(path)

    assert lib.default_client_id == "abrel_spv_2"
    assert "abrel_spv_2" in lib.clients
    c = lib.clients["abrel_spv_2"]
    assert c.client_name == "ABREL SPV 2 Limited"
    assert c.ref_prefix == "ABREL"
    assert c.kind_attn == "Kind Attn.: Mr. Rahul Patil"


def test_missing_file_returns_empty_library(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    lib = load_client_library(missing)

    assert lib.clients == {}
    assert lib.default_client_id is None


def test_malformed_json_returns_empty_library(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json", encoding="utf-8")

    lib = load_client_library(bad)

    assert lib.clients == {}
    assert lib.default_client_id is None


def test_duplicate_ids_falls_back_to_empty(tmp_path):
    path = _write_clients_file(tmp_path, {
        "clients": [
            {"id": "dup", "display_name": "A", "client_name": "A", "client_address": "X"},
            {"id": "dup", "display_name": "B", "client_name": "B", "client_address": "Y"},
        ],
    })

    lib = load_client_library(path)

    assert lib.clients == {}
    assert lib.default_client_id is None


def test_unknown_default_falls_back_to_first(tmp_path):
    path = _write_clients_file(tmp_path, {
        "default_client_id": "nonexistent",
        "clients": [
            {"id": "first", "display_name": "First", "client_name": "First Co", "client_address": "X"},
            {"id": "second", "display_name": "Second", "client_name": "Second Co", "client_address": "Y"},
        ],
    })

    lib = load_client_library(path)

    assert lib.default_client_id == "first"
    assert set(lib.clients.keys()) == {"first", "second"}


def test_invalid_id_regex_skips_entry(tmp_path):
    path = _write_clients_file(tmp_path, {
        "clients": [
            {"id": "valid_id", "display_name": "V", "client_name": "V Co", "client_address": "X"},
            {"id": "BAD ID!", "display_name": "B", "client_name": "B Co", "client_address": "Y"},
        ],
    })

    lib = load_client_library(path)

    assert "valid_id" in lib.clients
    assert "BAD ID!" not in lib.clients


def test_missing_required_fields_skips_entry(tmp_path):
    path = _write_clients_file(tmp_path, {
        "clients": [
            {"id": "good", "display_name": "G", "client_name": "G", "client_address": "X"},
            {"id": "bad", "display_name": "B"},  # missing client_name, client_address
        ],
    })

    lib = load_client_library(path)

    assert "good" in lib.clients
    assert "bad" not in lib.clients


def test_optional_fields_default_to_none(tmp_path):
    path = _write_clients_file(tmp_path, {
        "clients": [
            {
                "id": "minimal",
                "display_name": "Minimal Co",
                "client_name": "Minimal Co",
                "client_address": "Somewhere.",
            }
        ],
    })

    lib = load_client_library(path)
    c = lib.clients["minimal"]

    assert c.client_cin is None
    assert c.kind_attn is None
    assert c.ref_prefix is None
    assert c.reference_email_date is None


def test_library_get_returns_default_when_id_unknown(tmp_path):
    path = _write_clients_file(tmp_path, {
        "default_client_id": "primary",
        "clients": [
            {"id": "primary", "display_name": "P", "client_name": "P", "client_address": "X"},
        ],
    })

    lib = load_client_library(path)
    resolved = lib.resolve("does-not-exist")

    assert resolved is not None
    assert resolved.id == "primary"


def test_library_resolve_none_returns_default(tmp_path):
    path = _write_clients_file(tmp_path, {
        "default_client_id": "primary",
        "clients": [
            {"id": "primary", "display_name": "P", "client_name": "P", "client_address": "X"},
        ],
    })

    lib = load_client_library(path)

    assert lib.resolve(None).id == "primary"


def test_empty_library_resolve_returns_none(tmp_path):
    missing = tmp_path / "x.json"
    lib = load_client_library(missing)

    assert lib.resolve("anything") is None
    assert lib.resolve(None) is None


def test_top_level_not_object_returns_empty_library(tmp_path):
    p = tmp_path / "clients.json"
    p.write_text(json.dumps([{"id": "x"}]), encoding="utf-8")

    lib = load_client_library(p)

    assert lib.clients == {}
    assert lib.default_client_id is None


def test_non_dict_entry_in_list_is_skipped(tmp_path):
    path = _write_clients_file(tmp_path, {
        "clients": [
            "not a dict",
            42,
            {"id": "good", "display_name": "G", "client_name": "G", "client_address": "X"},
        ],
    })

    lib = load_client_library(path)

    assert set(lib.clients.keys()) == {"good"}


def test_clients_field_not_a_list_returns_empty_library(tmp_path):
    path = _write_clients_file(tmp_path, {
        "clients": {"id": "x"},
    })

    lib = load_client_library(path)

    assert lib.clients == {}
    assert lib.default_client_id is None


def test_get_client_library_is_cached():
    a = get_client_library()
    b = get_client_library()
    assert a is b
