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

# Load environment variables from .env file
echo "Step 0: Loading environment variables from .env file..."
ENV_FILE="./.env"
if [ -f "$ENV_FILE" ]; then
    echo "✅ Found .env file"
    # Export GEMINI_API_KEY from .env file
    export $(grep -v '^#' "$ENV_FILE" | grep 'GEMINI_API_KEY' | xargs)
    
    if [ -n "$GEMINI_API_KEY" ]; then
        echo "✅ Loaded GEMINI_API_KEY from .env file"
    else
        echo "⚠️  GEMINI_API_KEY not found in .env file"
    fi
else
    echo "⚠️  .env file not found at $ENV_FILE"
fi

# Build container image with cache busting
echo ""
echo "Step 1: Building container image..."
# BUILD_TIMESTAMP=$(date +%s)
BUILD_TIMESTAMP=1
echo "Build timestamp: $BUILD_TIMESTAMP (forces fresh build)"
gcloud builds submit --config=cloudbuild.yaml --project $PROJECT_ID \
    --substitutions=_IMAGE_TAG=$IMAGE_TAG,_CACHEBUST=$BUILD_TIMESTAMP

echo ""
echo "Step 2: Deploying to Cloud Run..."

# Verify GEMINI_API_KEY is set (either from .env or environment)
if [ -z "$GEMINI_API_KEY" ]; then
    echo ""
    echo "❌ ERROR: GEMINI_API_KEY is not set!"
    echo ""
    echo "Please add it to your .env file:"
    echo "  echo 'GEMINI_API_KEY=your-api-key-here' >> .env"
    echo ""
    echo "Or export it manually:"
    echo "  export GEMINI_API_KEY='your-api-key-here'"
    echo ""
    exit 1
fi

echo "✅ GEMINI_API_KEY is set (${GEMINI_API_KEY:0:20}...)"
echo ""

# Deploy with 4Gi memory and environment variables
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_TAG \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --cpu 1 \
    --timeout 3600 \
    --concurrency 1 \
    --max-instances 10 \
    --project $PROJECT_ID \
    --memory 4Gi \
    --set-env-vars="GEMINI_API_KEY=$GEMINI_API_KEY,GEMINI_MODEL_NAME=gemini-2.5-flash,CHROME_BIN=/usr/bin/chromium,CHROMEDRIVER_PATH=/usr/bin/chromedriver" 


echo ""
echo "✅ Deployment complete!"
echo "Service URL:"
gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)' --project $PROJECT_ID

echo ""
echo "Step 3: Cleaning up old revisions..."
# Get all revisions except the latest 3
OLD_REVISIONS=$(gcloud run revisions list \
    --service=$SERVICE_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format='value(metadata.name)' \
    --sort-by='~metadata.creationTimestamp' \
    | tail -n +4)

if [ -z "$OLD_REVISIONS" ]; then
    echo "No old revisions to delete."
else
    echo "Deleting old revisions:"
    for revision in $OLD_REVISIONS; do
        echo "  - Deleting $revision"
        gcloud run revisions delete $revision \
            --region=$REGION \
            --project=$PROJECT_ID \
            --quiet
    done
    echo "✅ Old revisions cleaned up!"
fi
