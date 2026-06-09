# AnyRoR scraper service (Cloud Run) — headless Chrome + the TSR scraper.
# Build from the REPO ROOT so the whole project is available:
#   docker build -f adk_agent/deploy/scraper_service/Dockerfile -t anyror-scraper .
FROM python:3.11-slim

# Headless Chromium + driver for Selenium.
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium chromium-driver fonts-indic \
        ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*
ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Base + ADK deps + the scraper service deps.
COPY requirements.txt requirements-adk.txt ./
COPY adk_agent/deploy/scraper_service/requirements.txt /tmp/svc-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r requirements-adk.txt -r /tmp/svc-requirements.txt

# Ship the project (tsr_generator, adk_agent, anyror, services, …).
COPY . .

# Cloud Run provides $PORT.
ENV PORT=8080
CMD exec uvicorn adk_agent.deploy.scraper_service.main:app --host 0.0.0.0 --port ${PORT}
