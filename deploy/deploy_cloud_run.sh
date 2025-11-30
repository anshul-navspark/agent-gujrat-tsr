#!/bin/bash
# Deployment script for Cloud Run
set -e

# Configuration
PROJECT_ID="neon-alcove-479309-q3"
SERVICE_NAME="gujrat-tsr-agent"
REGION="asia-south1"
IMAGE_TAG="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "=== Deploying to Cloud Run ==="
echo "Project: $PROJECT_ID"
echo "Service: $SERVICE_NAME"
echo "Region: $REGION"
echo ""

# Check for gcloud
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI is not installed."
    exit 1
fi

# Build container image
echo "Step 1: Building container image..."
gcloud builds submit --tag $IMAGE_TAG --project $PROJECT_ID

echo ""
echo "Step 2: Deploying to Cloud Run..."
# Deploy with 4Gi memory as requested
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_TAG \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory 4Gi \
    --timeout 300 \
    --project $PROJECT_ID

echo ""
echo "✅ Deployment complete!"
echo "Service URL:"
gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)' --project $PROJECT_ID
