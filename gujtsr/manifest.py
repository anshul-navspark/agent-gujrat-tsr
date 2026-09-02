"""What was fetched, from where, and how it may be described.

Until now this package wrote a PDF and checked it was over 1000 bytes. That
misses three things the other two state packages catch:

* **An error page saved with a .pdf name.** A WAF interstitial is comfortably
  over 1000 bytes and sits in a matter folder looking like a record.
* **The portal repeating itself.** AnyRoR after a failed postback re-serves the
  previous survey's record with a fresh header; byte-identical documents under
  two different kinds is the only signal that happened.
* **Provenance.** Nothing recorded which portal a file came from, or that it is
  not certified.

Nothing here reads a document. It asserts a `%PDF` header, checksums the bytes,
and derives how the document may be described from the LANE that produced it --
a fact the fetch layer knows, and one a caller should not get to assert, because
overstating certification is the error nobody downstream would catch.

Neither Gujarat portal yields anything certified. AnyRoR's record is an
uncertified online copy, and Garvi returns unsealed index data that is expressly
not an Encumbrance Certificate and not annexable.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

#: lane -> how a document from it may be described. `certified` is False
#: throughout and is not a default a caller may override: nothing on either of
#: these free paths is a certified copy.
LANE_PROVENANCE = {
    "anyror_record": {
        "provenance": "Online Copy (uncertified)",
        "source": "AnyRoR — Integrated Survey No. Details",
        "certified": False,
    },
    "garvi_index": {
        "provenance": "Unsealed index data — NOT an Encumbrance Certificate",
        "source": "Garvi — Sub-Registrar property search",
        "certified": False,
    },
}


class NotAPdf(ValueError):
    """The saved bytes are not a PDF. A block page saved as .pdf produced one."""


class DuplicateDocument(ValueError):
    """Two different documents came back byte-identical — the portal repeated itself."""


class UnknownLane(ValueError):
    """The lane is not one this package knows how to describe."""


class Manifest:
    def __init__(self, path, survey: str, village: dict):
        self.path, self.survey, self.village = Path(path), survey, village
        self.fetched: list[dict] = []
        self.not_found: list[dict] = []

    def record(self, kind: str, source, portal: str, lane: str, **extra) -> dict:
        source = Path(source)
        data = source.read_bytes()
        if not data.startswith(b"%PDF"):
            raise NotAPdf(
                f"{source.name} does not start with %PDF — refusing to record it. "
                f"A WAF block page is comfortably larger than the old size check and "
                f"would have passed it."
            )
        if lane not in LANE_PROVENANCE:
            raise UnknownLane(
                f"unknown lane {lane!r}. Known lanes: {', '.join(sorted(LANE_PROVENANCE))}"
            )

        digest = hashlib.sha256(data).hexdigest()
        clash = next((e for e in self.fetched
                      if e["sha256"] == digest and e["kind"] != kind), None)
        if clash is not None:
            raise DuplicateDocument(
                f"{kind} is byte-identical to {clash['kind']} — AnyRoR re-serves the "
                f"previous survey's record after a failed postback. Re-fetch on a "
                f"fresh session before trusting either."
            )

        described = LANE_PROVENANCE[lane]
        # `extra` first so a caller may add fields but never overwrite a derived
        # one — certified in particular is an invariant, not a default.
        entry = {
            **extra,
            "kind": kind, "portal": portal, "lane": lane,
            "path": source.name, "sha256": digest, "pdf_header_ok": True,
            **described,
            "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        }
        self.fetched.append(entry)
        return entry

    def record_absent(self, kind: str, query: dict, blocked_on: str, reason: str) -> dict:
        """What was looked for and not obtained, carrying the STAGE it stopped at.

        Garvi stopping at the OTP is not a failure to hide — it is what the
        requisition list is built from, and `blocked_on` is what distinguishes it
        from a search that ran and found nothing.
        """
        entry = {"kind": kind, "query": query, "blocked_on": blocked_on, "reason": reason}
        self.not_found.append(entry)
        return entry

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "survey": self.survey, "village": self.village,
            "fetched": self.fetched, "not_found": self.not_found,
        }, ensure_ascii=False, indent=2) + "\n")
        return self.path
