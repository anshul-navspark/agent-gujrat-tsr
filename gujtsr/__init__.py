"""gujtsr — the four capabilities that matter, behind one small surface.

The rest of this repo (FastAPI, Streamlit, the MCP server, the GCS cache) is
optional packaging around these. This package deliberately depends on none of
it, so a QM skill sandbox can run it with requests + python-docx + a Chrome
binary and nothing else.

    fetch   village + survey -> land-record PDF   (AnyRoR, via residential proxy)
    text    PDF -> plain text                     (deterministic, no model)
    render  extraction JSON -> TSR .docx          (deterministic, no model)

Extraction (text -> JSON) is the one step that needs a model. It lives in
`gujtsr.extract`, which can either shell out to `claude -p` or hand the text
back to a calling agent; the drafting rules both paths follow are in
`references/extraction-rules.md` so they cannot drift apart.
"""

__all__ = ["fetch", "text", "render"]
