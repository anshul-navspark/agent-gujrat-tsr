# Deploying Gujarat TSR Agent to Streamlit Cloud

This guide explains how to deploy the Gujarat TSR Agent UI to Streamlit Cloud while using the Google Cloud Run API for backend processing.

## Architecture

```
┌─────────────────────┐
│  Streamlit Cloud    │
│  (UI Only)          │
└──────────┬──────────┘
           │ HTTPS
           ▼
┌─────────────────────┐
│  Cloud Run API      │
│  (PDF + TSR)        │
└─────────────────────┘
```

## Prerequisites

1. **GitHub Repository**: Your code must be in a GitHub repository
2. **Cloud Run API**: The backend API must be deployed and accessible
3. **Streamlit Cloud Account**: Sign up at [share.streamlit.io](https://share.streamlit.io)

## Deployment Steps

### 1. Prepare Your Repository

Ensure these files are in your repository:

- `app/streamlit_app_cloud.py` - The Streamlit Cloud app
- `app/api_client.py` - API client for Cloud Run
- `requirements_streamlit.txt` - Streamlit Cloud dependencies
- `.streamlit/config.toml` - Streamlit configuration
- `.streamlit/secrets.toml.example` - Example secrets file

### 2. Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "New app"
3. Select your GitHub repository
4. Configure the app:
   - **Main file path**: `app/streamlit_app_cloud.py`
   - **Python version**: 3.9 or higher
   - **Requirements file**: `requirements_streamlit.txt`

### 3. Configure Secrets

In the Streamlit Cloud dashboard:

1. Go to your app settings
2. Click on "Secrets"
3. Add the following secrets:

```toml
API_URL = "https://gujrat-tsr-agent-5vu5tfjlga-el.a.run.app"
API_TIMEOUT = 600
API_MAX_RETRIES = 2
```

### 4. Deploy

Click "Deploy" and wait for the app to build and start.

## Verification

Once deployed:

1. **Check API Health**: Use the "Check API Health" button in the sidebar
2. **Test Single Record**: Process a single record to verify end-to-end functionality
3. **Test Batch Processing**: Upload a small Excel file (5-10 records) to test batch processing

## Troubleshooting

### App Won't Start

**Error**: `ModuleNotFoundError: No module named 'api_client'`

**Solution**: Ensure `app/api_client.py` exists and the main file path is set to `app/streamlit_app_cloud.py`

---

### API Health Check Fails

**Error**: "❌ API is not responding"

**Solutions**:
1. Verify the API URL in secrets is correct
2. Check if Cloud Run service is running: `gcloud run services list --project neon-alcove-479309-q3`
3. Test the API directly: `curl https://your-api-url/health`

---

### Timeout Errors

**Error**: "Request timed out after 600 seconds"

**Solutions**:
1. Increase `API_TIMEOUT` in secrets (max 900 seconds)
2. Check Cloud Run logs for backend issues
3. Verify the record exists in the AnyRoR system

---

### Import Errors

**Error**: `ImportError: cannot import name 'TSRAPIClient'`

**Solution**: Ensure `api_client.py` is in the same directory as `streamlit_app_cloud.py`

## Updating the App

To update your deployed app:

1. Push changes to your GitHub repository
2. Streamlit Cloud will automatically rebuild and redeploy
3. Monitor the deployment logs in the Streamlit Cloud dashboard

## Cost Considerations

### Streamlit Cloud
- **Free tier**: 1 private app, unlimited public apps
- **Cost**: Free for public apps

### Cloud Run API
- **Pricing**: Pay per request
- **Free tier**: 2 million requests/month
- **Estimated cost**: ~$0.01-0.05 per 100 records (very rough estimate)

## Monitoring

### Streamlit Cloud
- View app logs in the Streamlit Cloud dashboard
- Monitor app usage and performance

### Cloud Run
```bash
# View recent logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=gujrat-tsr-agent" --limit 50 --project neon-alcove-479309-q3

# Monitor requests
gcloud run services describe gujrat-tsr-agent --region asia-south1 --project neon-alcove-479309-q3
```

## Security

1. **Never commit secrets**: `.streamlit/secrets.toml` is in `.gitignore`
2. **API Authentication**: Consider adding API key authentication to Cloud Run
3. **HTTPS**: Both Streamlit Cloud and Cloud Run use HTTPS by default

## Support

For issues:
1. Check Streamlit Cloud logs
2. Check Cloud Run logs
3. Review this documentation
4. Contact support if needed

## Next Steps

- Set up monitoring and alerting
- Add authentication to the Streamlit app
- Implement rate limiting on the API
- Add caching for frequently accessed records
