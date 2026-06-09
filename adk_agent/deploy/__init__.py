"""
Enterprise deployment scaffolding for the TSR ADK agent.

* :mod:`adk_agent.deploy.agent_engine_app` — wraps the ADK ``root_agent`` for
  deployment to **Vertex AI Agent Engine** (the managed runtime behind Gemini
  Enterprise).
* ``scraper_service/`` — a standalone **Cloud Run** service that runs the
  Selenium AnyRoR scrape (the one component that can't live in the managed agent
  runtime), exposed to the agent as a tool over HTTPS.
* ``env.example`` + ``README.md`` — the env_file and the deploy runbook.

See ``README.md`` for the end-to-end deploy steps.
"""
