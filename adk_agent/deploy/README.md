# Deploy the TSR agent as an enterprise agent

Run the ADK TSR agent on **Vertex AI Agent Engine** (the managed runtime behind
**Gemini Enterprise**), authenticated by a **service account** — no personal API
key, enterprise quota. The one piece that can't live in the managed runtime (the
Selenium AnyRoR scrape) runs as a separate **Cloud Run** service the agent calls
as a tool.

```
Gemini Enterprise (registry/UI)
      │ register
      ▼
Vertex AI Agent Engine ── ADK root_agent (ingest → extract → assemble)
      │  ANYROR_SCRAPER_URL (HTTPS, survey mode only)
      ▼
Cloud Run: anyror-scraper ── Selenium + headless Chrome + CAPTCHA
      │  egress: Cloud NAT / VPN with an India-routable IP
      ▼
   anyror.gujarat.gov.in
```

> PDF mode (you already have the PDF) needs **none** of the scraper/egress — only
> the agent + Vertex auth.

## 0. Prereqs

```bash
gcloud config set project "$GOOGLE_CLOUD_PROJECT"
gcloud services enable aiplatform.googleapis.com run.googleapis.com \
    cloudbuild.googleapis.com secretmanager.googleapis.com
pip install -r requirements.txt -r requirements-adk.txt \
    "google-cloud-aiplatform[agent_engines]"
```

## 1. Service account (no key files in prod)

```bash
gcloud iam service-accounts create tsr-agent --display-name "TSR Agent"
SA="tsr-agent@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member="serviceAccount:$SA" --role="roles/aiplatform.user"
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member="serviceAccount:$SA" --role="roles/discoveryengine.editor"   # Gemini Enterprise
# Local dev uses ADC instead of a key:  gcloud auth application-default login
```

## 2. (Survey mode) deploy the scraper to Cloud Run with India egress

```bash
# Build from the repo root (the Dockerfile COPYs the whole project).
gcloud builds submit --tag "gcr.io/$GOOGLE_CLOUD_PROJECT/anyror-scraper" \
    --file adk_agent/deploy/scraper_service/Dockerfile .

# Egress must exit from an India-routable IP (AnyRoR is geo-blocked otherwise):
# attach a Serverless VPC connector in asia-south1 + Cloud NAT, or a VPN to an
# India endpoint. Then deploy:
gcloud run deploy anyror-scraper \
    --image "gcr.io/$GOOGLE_CLOUD_PROJECT/anyror-scraper" \
    --region asia-south1 --no-allow-unauthenticated \
    --service-account "$SA" \
    --vpc-connector india-egress --vpc-egress all-traffic \
    --set-secrets "ANYROR_SCRAPER_TOKEN=anyror-scraper-token:latest,GEMINI_API_KEY=gemini-key:latest" \
    --memory 2Gi --cpu 2 --timeout 600

export ANYROR_SCRAPER_URL="$(gcloud run services describe anyror-scraper \
    --region asia-south1 --format 'value(status.url)')"
```

> The scraper still needs a Gemini key (or Vertex) for the **CAPTCHA solver**;
> that's local to the scraper service, not the agent.

## 3. Deploy the agent to Agent Engine

```bash
# Fill in adk_agent/deploy/env.example -> env.prod (GOOGLE_CLOUD_PROJECT,
# GOOGLE_CLOUD_LOCATION, GEMINI_MODEL_NAME, ANYROR_SCRAPER_URL/TOKEN).

# Option A — ADK CLI:
adk deploy agent_engine \
    --project="$GOOGLE_CLOUD_PROJECT" --region="$GOOGLE_CLOUD_LOCATION" \
    --staging_bucket="gs://${GOOGLE_CLOUD_PROJECT}-agent-staging" \
    --env_file=adk_agent/deploy/env.prod \
    adk_agent

# Option B — programmatic:
GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT \
ANYROR_SCRAPER_URL=$ANYROR_SCRAPER_URL \
    python -m adk_agent.deploy.agent_engine_app deploy
```

## 4. Register with Gemini Enterprise

Register the deployed Agent Engine resource so it's usable in the Gemini
Enterprise UI / Agents API — see
[Register and manage an ADK agent](https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-adk-agent).

## Notes

- **No personal API key.** The agent authenticates via Vertex AI + the service
  account (`GOOGLE_GENAI_USE_VERTEXAI=1`); `AdkConfig.has_credentials` recognises
  Vertex mode so the agent reaches the real backend (never the offline fake).
- **Secrets** live in Secret Manager (`--set-secrets`), never in `env.*`.
- **The geo-block is a network problem, not an auth one** — it's solved by the
  scraper's India egress, independent of the key/quota.
