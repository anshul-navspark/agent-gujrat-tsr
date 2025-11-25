# Google Cloud Setup Guide

## Step 1: Install Google Cloud CLI

### For macOS (your system):

```bash
# Download and install using the official installer
curl https://sdk.cloud.google.com | bash

# Restart your shell or run:
exec -l $SHELL

# Initialize gcloud
gcloud init
```

**Alternative: Install via Homebrew (recommended)**
```bash
brew install --cask google-cloud-sdk
```

### For Linux:
```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud init
```

### For Windows:
Download the installer from: https://cloud.google.com/sdk/docs/install

## Step 2: Authenticate with Google Cloud

```bash
gcloud auth login
```

This will open a browser window for you to sign in with your Google account.

## Step 3: Create a New GCP Project

```bash
# Set a project ID (must be globally unique)
export PROJECT_ID="gujrat-tsr-agent-$(date +%s)"

# Create the project
gcloud projects create $PROJECT_ID --name="Gujarat TSR Agent"

# Set as default project
gcloud config set project $PROJECT_ID

# Verify
gcloud config list project
```

## Step 4: Enable Billing

You need to link a billing account to your project:

```bash
# List available billing accounts
gcloud billing accounts list

# Link billing account to project (replace BILLING_ACCOUNT_ID)
gcloud billing projects link $PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
```

**Or enable billing via Console:**
1. Go to https://console.cloud.google.com/billing
2. Select your project
3. Link a billing account

## Step 5: Enable Required APIs

```bash
# Enable Compute Engine API
gcloud services enable compute.googleapis.com

# Enable other useful APIs
gcloud services enable \
    cloudresourcemanager.googleapis.com \
    serviceusage.googleapis.com \
    logging.googleapis.com \
    monitoring.googleapis.com
```

## Step 6: Set Default Region and Zone

```bash
# Set default region and zone
gcloud config set compute/region us-central1
gcloud config set compute/zone us-central1-a

# Verify configuration
gcloud config list
```

## Step 7: Update Deployment Scripts

After creating your project, update the deployment script:

```bash
# Get your project ID
PROJECT_ID=$(gcloud config get-value project)
echo "Your project ID is: $PROJECT_ID"

# Update deploy.sh
sed -i '' "s/PROJECT_ID=\"your-project-id\"/PROJECT_ID=\"$PROJECT_ID\"/" deploy/deploy.sh
```

## Quick Setup Script

Save this as `setup_gcp.sh` and run it:

```bash
#!/bin/bash
set -e

echo "=== Google Cloud Project Setup ==="

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "gcloud CLI is not installed. Installing via Homebrew..."
    brew install --cask google-cloud-sdk
fi

# Authenticate
echo "Authenticating with Google Cloud..."
gcloud auth login

# Create project
PROJECT_ID="gujrat-tsr-agent-$(date +%s)"
echo "Creating project: $PROJECT_ID"
gcloud projects create $PROJECT_ID --name="Gujarat TSR Agent"

# Set as default
gcloud config set project $PROJECT_ID

# Set region/zone
gcloud config set compute/region us-central1
gcloud config set compute/zone us-central1-a

echo ""
echo "✅ Project created: $PROJECT_ID"
echo ""
echo "⚠️  IMPORTANT: You need to enable billing for this project"
echo "Visit: https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID"
echo ""
echo "After enabling billing, run:"
echo "  gcloud services enable compute.googleapis.com"
echo ""
echo "Then you can deploy with:"
echo "  ./deploy/deploy.sh"
```

## Verification

Check your setup:

```bash
# Check authentication
gcloud auth list

# Check current project
gcloud config get-value project

# Check enabled services
gcloud services list --enabled

# Check compute quotas
gcloud compute project-info describe --project=$(gcloud config get-value project)
```

## Troubleshooting

### "gcloud: command not found"
- Restart your terminal after installation
- Or run: `source ~/.bashrc` or `source ~/.zshrc`

### "Billing is not enabled"
- Go to https://console.cloud.google.com/billing
- Create or link a billing account
- Enable billing for your project

### "API not enabled"
- Run: `gcloud services enable compute.googleapis.com`
- Or enable via Console: https://console.cloud.google.com/apis

## Next Steps

After completing this setup:
1. ✅ Install gcloud CLI
2. ✅ Authenticate
3. ✅ Create project
4. ✅ Enable billing
5. ✅ Enable APIs
6. ⬜ Deploy your app with `./deploy/deploy.sh`
