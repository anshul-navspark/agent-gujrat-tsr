"""
Vertex AI Agent Engine entrypoint.

Wraps the existing ADK ``root_agent`` (the ``ingest -> extractor -> assemble``
graph) as an ``AdkApp`` and deploys it to **Vertex AI Agent Engine** — the
managed runtime that Gemini Enterprise registers and serves. Auth is via the
deployment's **service account + ADC** (no personal API key); see
``AdkConfig`` (``GOOGLE_GENAI_USE_VERTEXAI=1``).

Two ways to deploy:

    # 1. ADK CLI (uses adk_agent/graph.py::root_agent + an env_file)
    adk deploy agent_engine \\
        --project=$GOOGLE_CLOUD_PROJECT --region=$GOOGLE_CLOUD_LOCATION \\
        --staging_bucket=gs://$GOOGLE_CLOUD_PROJECT-agent-staging \\
        --env_file=adk_agent/deploy/env.example \\
        adk_agent

    # 2. Programmatic (this module)
    python -m adk_agent.deploy.agent_engine_app deploy

Heavy SDKs (vertexai) are imported lazily so importing this module — e.g. for
``get_adk_app()`` in tests — never requires them.
"""

from __future__ import annotations

import os
import sys

# The deployable agent (already defined; reused, not redefined).
from adk_agent.graph import root_agent  # noqa: F401  (re-exported for `adk deploy`)


def get_adk_app():
    """Build the Vertex ``AdkApp`` wrapping the TSR root agent (tracing enabled)."""
    from vertexai.preview.reasoning_engines import AdkApp  # lazy

    return AdkApp(agent=root_agent, enable_tracing=True)


def deploy(
    *,
    project: str | None = None,
    location: str | None = None,
    staging_bucket: str | None = None,
    display_name: str = "gujarat-tsr-agent",
):
    """
    Create (or update) the Agent Engine deployment.

    Reads project/location/bucket from args or the standard env vars. Requirements
    are taken from the repo's ``requirements*.txt`` so the deployed container
    matches local behaviour (the Selenium scraper is NOT needed here — it runs as
    a separate Cloud Run service the agent calls via ``ANYROR_SCRAPER_URL``).
    """
    import vertexai
    from vertexai import agent_engines

    project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
    location = location or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    staging_bucket = staging_bucket or os.getenv("STAGING_BUCKET") or (
        f"gs://{project}-agent-staging" if project else None
    )
    if not project or not staging_bucket:
        raise SystemExit(
            "Set GOOGLE_CLOUD_PROJECT (and optionally STAGING_BUCKET / "
            "GOOGLE_CLOUD_LOCATION) before deploying."
        )

    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    requirements = ["google-adk>=2.2.0", "google-cloud-aiplatform[agent_engines]", "python-docx", "pypdf"]
    env_vars = {
        "GOOGLE_GENAI_USE_VERTEXAI": "1",
        "GEMINI_MODEL_NAME": os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-pro-preview"),
    }
    # Forward the scraper-tool wiring if configured.
    for k in ("ANYROR_SCRAPER_URL", "ANYROR_SCRAPER_TOKEN"):
        if os.getenv(k):
            env_vars[k] = os.environ[k]

    print(f"Deploying '{display_name}' to Agent Engine ({project}/{location}) …")
    remote = agent_engines.create(
        get_adk_app(),
        display_name=display_name,
        requirements=requirements,
        extra_packages=[here],          # ship the repo (tsr_generator, adk_agent, anyror)
        env_vars=env_vars,
    )
    print("Deployed. resource_name:", remote.resource_name)
    print("Register it with Gemini Enterprise — see adk_agent/deploy/README.md.")
    return remote


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        deploy()
    else:
        print(__doc__)
