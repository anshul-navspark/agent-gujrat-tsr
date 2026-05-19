"""
Client library: load and validate clients.json so the team can save
lender/client details and pick the active one from the Streamlit UI.

The file lives at the repo root by default. If it is missing or malformed,
the loader returns an empty library — the DOCX template's hardcoded ABREL
fallback then takes over, preserving existing behavior.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Union


logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9_-]+$")
_REQUIRED_FIELDS = ("id", "display_name", "client_name", "client_address")


@dataclass(frozen=True)
class Client:
    """A single client/lender entry from the library."""

    id: str
    display_name: str
    client_name: str
    client_address: str
    client_cin: Optional[str] = None
    kind_attn: Optional[str] = None
    ref_prefix: Optional[str] = None
    reference_email_date: Optional[str] = None


@dataclass
class ClientLibrary:
    """The full set of clients loaded from clients.json."""

    clients: Dict[str, Client] = field(default_factory=dict)
    default_client_id: Optional[str] = None

    def resolve(self, client_id: Optional[str]) -> Optional[Client]:
        """
        Look up a client by id. If the id is None or unknown, fall back to
        the default client. Returns None only when the library is empty.
        """
        if not self.clients:
            return None
        if client_id and client_id in self.clients:
            return self.clients[client_id]
        if self.default_client_id and self.default_client_id in self.clients:
            return self.clients[self.default_client_id]
        return None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_client_library(path: Union[str, Path, None] = None) -> ClientLibrary:
    """
    Load clients.json and return a validated ClientLibrary.

    Validation failures (missing file, malformed JSON, duplicate ids,
    invalid id chars, missing required fields) never raise — they log
    and return whatever portion of the library is valid. Duplicate ids
    are treated as a hard error and yield an empty library because the
    intent is ambiguous.
    """
    if path is None:
        path = _project_root() / "clients.json"
    path = Path(path)

    if not path.exists():
        logger.warning("clients.json not found at %s — using empty library", path)
        return ClientLibrary()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to parse %s: %s", path, exc)
        return ClientLibrary()

    if not isinstance(raw, dict):
        logger.error("clients.json must be a JSON object, got %r", type(raw).__name__)
        return ClientLibrary()

    raw_clients = raw.get("clients") or []
    if not isinstance(raw_clients, list):
        logger.error("clients.json 'clients' must be a list, got %r", type(raw_clients).__name__)
        return ClientLibrary()

    # First pass: detect duplicate ids
    ids_seen = [entry.get("id") for entry in raw_clients if isinstance(entry, dict)]
    duplicates = {i for i in ids_seen if ids_seen.count(i) > 1 and i}
    if duplicates:
        logger.error("clients.json has duplicate ids %s — returning empty library", duplicates)
        return ClientLibrary()

    clients: Dict[str, Client] = {}
    for idx, entry in enumerate(raw_clients):
        if not isinstance(entry, dict):
            logger.warning("clients[%d] is not an object — skipping", idx)
            continue
        missing = [f for f in _REQUIRED_FIELDS if not entry.get(f)]
        if missing:
            logger.warning("clients[%d] missing required fields %s — skipping", idx, missing)
            continue
        client_id = entry["id"]
        if not _ID_RE.match(client_id):
            logger.warning("clients[%d] id %r does not match %s — skipping", idx, client_id, _ID_RE.pattern)
            continue
        clients[client_id] = Client(
            id=client_id,
            display_name=entry["display_name"],
            client_name=entry["client_name"],
            client_address=entry["client_address"],
            client_cin=entry.get("client_cin") or None,
            kind_attn=entry.get("kind_attn") or None,
            ref_prefix=entry.get("ref_prefix") or None,
            reference_email_date=entry.get("reference_email_date") or None,
        )

    default_id = raw.get("default_client_id")
    if default_id and default_id not in clients:
        logger.warning(
            "default_client_id %r not found in clients — falling back to first entry",
            default_id,
        )
        default_id = None
    if not default_id and clients:
        default_id = next(iter(clients))

    for c in clients.values():
        logger.info("Loaded client: id=%s display_name=%r", c.id, c.display_name)
    if default_id:
        logger.info("Default client: %s", default_id)

    return ClientLibrary(clients=clients, default_client_id=default_id)


@lru_cache(maxsize=1)
def get_client_library() -> ClientLibrary:
    """Singleton accessor — loads once per process."""
    return load_client_library()
