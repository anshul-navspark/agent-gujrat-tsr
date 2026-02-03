# Streamlit Cloud Setup Guide

This guide explains how to properly set up the Gujarat TSR Agent on Streamlit Cloud with automatic cache clearing and Cloud Run integration.

## Architecture Overview

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   GitHub Repo       │     │  Streamlit Cloud    │     │  Google Cloud Run   │
│                     │────▶│  (UI Frontend)      │────▶│  (Backend API)      │
│  - Code changes     │     │  - streamlit_app_   │     │  - PDF scraping     │
│  - GitHub Actions   │     │    cloud.py         │     │  - TSR generation   │
│                     │     │                     │     │  - GCS caching      │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
         │                                                        │
         │                                                        │
         ▼                                                        ▼
┌─────────────────────┐                              ┌─────────────────────┐
│  GitHub Actions     │──────────────────────────────│  Google Cloud       │
│  - Clear cache on   │                              │  Storage (GCS)      │
│    code push        │                              │  - DOCX cache       │
│  - Trigger rebuild  │                              │  - PDF cache        │
└─────────────────────┘                              └─────────────────────┘
```

## Prerequisites

1. **GitHub Repository** - Your code in a GitHub repo
2. **Google Cloud Project** - With Cloud Run and Cloud Build enabled
3. **Streamlit Cloud Account** - Connected to your GitHub account
4. **Google Cloud Service Account** - With permissions for Cloud Run and GCS

## Step 1: Configure Google Cloud

### 1.1 Create a Service Account for GitHub Actions

```bash
# Set your project ID
PROJECT_ID=your-project-id

# Create service account
gcloud iam service-accounts create github-actions \
    --display-name="GitHub Actions"

# Grant required permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/run.developer"

# Create and download key
gcloud iam service-accounts keys create github-actions-key.json \
    --iam-account=github-actions@$PROJECT_ID.iam.gserviceaccount.com
```

### 1.2 Create GCS Bucket for Cache

```bash
gsutil mb -l asia-south1 gs://$PROJECT_ID-tsr-cache
```

## Step 2: Configure GitHub Secrets

Go to your GitHub repository → Settings → Secrets and variables → Actions

Add these secrets:

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `GCP_PROJECT_ID` | Your Google Cloud project ID | `neon-alcove-479309-q3` |
| `GCP_SA_KEY` | Service account JSON key (entire content) | `{"type": "service_account", ...}` |

## Step 3: Configure Streamlit Cloud

### 3.1 Connect Your App

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "New app"
3. Connect your GitHub repository
4. Set the main file path to: `app/streamlit_app_cloud.py`

### 3.2 Add Secrets

In Streamlit Cloud dashboard → Your App → Settings → Secrets:

```toml
# REQUIRED: Cloud Run API URL
API_URL = "https://agent-gujarat-tsr-642363716512.asia-south1.run.app"

# REQUIRED: API timeout (seconds)
API_TIMEOUT = 900

# REQUIRED: Max retry attempts
API_MAX_RETRIES = 2

# OPTIONAL: Max parallel workers for batch processing
MAX_WORKERS = 30

# OPTIONAL: Only if you want to display Gemini-related features
# GEMINI_API_KEY = "your-key-here"
```

## Step 4: Verify the Setup

### 4.1 Test Cloud Run Health

```bash
curl https://agent-gujarat-tsr-642363716512.asia-south1.run.app/health
# Expected: {"status": "healthy"}
```

### 4.2 Test Cache Clearing

```bash
curl -X POST https://agent-gujarat-tsr-642363716512.asia-south1.run.app/clear-docx-cache \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
# Expected: {"status": "success", "message": "Cleared X DOCX files from cache", ...}
```

### 4.3 Test GitHub Actions

1. Make a small code change
2. Commit and push to main branch
3. Check GitHub Actions tab for the workflow run
4. Verify cache was cleared in the workflow logs

## Troubleshooting

### Streamlit App Shows Error

1. **Check Secrets**: Ensure all secrets are correctly configured in Streamlit Cloud
2. **Check API URL**: Verify the Cloud Run service is running and accessible
3. **Check Logs**: View Streamlit Cloud logs for detailed error messages

### Cache Not Clearing

1. **Check GitHub Actions**: Look at the workflow run logs
2. **Check Permissions**: Ensure the service account has storage.admin role
3. **Manual Clear**: Use the `/clear-docx-cache` API endpoint directly

### API Calls Failing

1. **Check Cloud Run Logs**: Look for errors in Google Cloud Console
2. **Check Timeouts**: Increase `API_TIMEOUT` if processing takes too long
3. **Check CORS**: Ensure Cloud Run allows requests from Streamlit Cloud

## Automatic Cache Clearing Flow

When you push code changes:

1. **GitHub Actions Triggered**: `clear-cache-on-push.yml` workflow runs
2. **Cache Cleared**: Workflow calls `/clear-docx-cache` endpoint or uses gsutil
3. **Version Updated**: `deployed_version.txt` in GCS is updated with commit SHA
4. **Cloud Build Deploys**: (If configured) New code is deployed to Cloud Run
5. **Streamlit Syncs**: Streamlit Cloud automatically pulls the latest code

## Manual Cache Clearing

If automatic clearing fails, you can manually clear the cache:

### Option 1: Via API
```bash
curl -X POST https://your-cloud-run-url/clear-docx-cache \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

### Option 2: Via gsutil
```bash
gsutil -m rm gs://your-project-id-tsr-cache/cache/**/tsr.docx
```

### Option 3: Via Python Script
```bash
cd /path/to/repo
python scripts/manual_clear_cache.py
```

## Contact

For issues with this setup, check:
1. GitHub Actions logs
2. Streamlit Cloud logs
3. Google Cloud Console (Cloud Run and Cloud Build)
