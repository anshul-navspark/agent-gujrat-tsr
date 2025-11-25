#!/bin/bash
# Quick setup script for Google Cloud Project
set -e

echo "=== Google Cloud Project Setup for Gujarat TSR Agent ==="
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI is not installed."
    echo ""
    echo "Installing via Homebrew..."
    if ! command -v brew &> /dev/null; then
        echo "❌ Homebrew is not installed either."
        echo "Please install Homebrew first: https://brew.sh"
        echo "Or install gcloud manually: https://cloud.google.com/sdk/docs/install"
        exit 1
    fi
    
    brew install --cask google-cloud-sdk
    
    echo ""
    echo "✅ gcloud CLI installed"
    echo "⚠️  Please restart your terminal and run this script again"
    exit 0
fi

echo "✅ gcloud CLI is installed"
echo ""

# Authenticate
echo "Step 1: Authenticating with Google Cloud..."
echo "This will open a browser window for you to sign in."
read -p "Press Enter to continue..."
gcloud auth login

echo ""
echo "✅ Authentication complete"
echo ""

# Create project with unique ID
PROJECT_ID="neon-alcove-479309-q3"
echo "Step 2: Creating new project: $PROJECT_ID"
gcloud projects create $PROJECT_ID --name="Gujarat TSR Agent"

echo ""
echo "✅ Project created"
echo ""

# Set as default project
echo "Step 3: Setting as default project..."
gcloud config set project $PROJECT_ID

# Set default region and zone (Mumbai - closest to Jaipur)
echo "Step 4: Setting default region and zone..."
gcloud config set compute/region asia-south1
gcloud config set compute/zone asia-south1-a

echo ""
echo "✅ Configuration complete"
echo ""

# Display project info
echo "=== Project Information ==="
echo "Project ID: $PROJECT_ID"
echo "Project Name: Gujarat TSR Agent"
echo "Region: asia-south1 (Mumbai)"
echo "Zone: asia-south1-a"
echo ""

# Update deploy.sh with project ID
echo "Step 5: Updating deployment script..."
if [ -f "deploy/deploy.sh" ]; then
    # Use different sed syntax for macOS
    sed -i '' "s/PROJECT_ID=\"your-project-id\"/PROJECT_ID=\"$PROJECT_ID\"/" deploy/deploy.sh
    echo "✅ Updated deploy/deploy.sh with project ID"
else
    echo "⚠️  deploy/deploy.sh not found, skipping update"
fi

echo ""
echo "=== ⚠️  IMPORTANT NEXT STEPS ==="
echo ""
echo "1. Enable billing for your project:"
echo "   Visit: https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID"
echo ""
echo "2. After enabling billing, enable required APIs:"
echo "   gcloud services enable compute.googleapis.com"
echo ""
echo "3. List available billing accounts (if needed):"
echo "   gcloud billing accounts list"
echo ""
echo "4. Link billing account (replace BILLING_ACCOUNT_ID):"
echo "   gcloud billing projects link $PROJECT_ID --billing-account=BILLING_ACCOUNT_ID"
echo ""
echo "5. Once billing is enabled, deploy your app:"
echo "   ./deploy/deploy.sh"
echo ""
echo "=== Setup Complete! ==="
