#!/bin/bash
# Deployment helper script for GCE
# This script helps deploy updates to the running GCE instance

set -e

# Configuration
GCE_INSTANCE_NAME="gujrat-tsr-agent"  # Change this to your instance name
GCE_ZONE="asia-south1-a"              # Mumbai region - closest to Jaipur
PROJECT_ID="neon-alcove-479309-q3"          # Change this to your GCP project ID

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Gujarat TSR Agent - GCE Deployment Helper${NC}"
echo ""

# Function to check if gcloud is installed
check_gcloud() {
    if ! command -v gcloud &> /dev/null; then
        echo -e "${RED}Error: gcloud CLI is not installed${NC}"
        echo "Please install it from: https://cloud.google.com/sdk/docs/install"
        exit 1
    fi
}

# Function to create a new GCE instance
create_instance() {
    echo -e "${YELLOW}Creating new GCE instance...${NC}"
    
    gcloud compute instances create $GCE_INSTANCE_NAME \
        --project=$PROJECT_ID \
        --zone=$GCE_ZONE \
        --machine-type=e2-standard-2 \
        --boot-disk-size=50GB \
        --boot-disk-type=pd-standard \
        --image-family=debian-11 \
        --image-project=debian-cloud \
        --metadata-from-file startup-script=deploy/gce_startup.sh \
        --tags=http-server,https-server \
        --scopes=cloud-platform
    
    echo -e "${GREEN}Instance created successfully!${NC}"
    echo "Waiting for startup script to complete (this may take 5-10 minutes)..."
    sleep 300
}

# Function to deploy updates
deploy_updates() {
    echo -e "${YELLOW}Deploying updates to existing instance...${NC}"
    
    # Copy files to instance using rsync (gcloud scp doesn't support --exclude)
    echo "Syncing files to instance..."
    
    # Wait for startup script to complete (check if apt-get is running)
    echo "Checking if startup script is still running..."
    while gcloud compute ssh $GCE_INSTANCE_NAME \
        --project=$PROJECT_ID \
        --zone=$GCE_ZONE \
        --command="pgrep -f 'apt-get|dpkg' >/dev/null 2>&1"; do
        echo "Startup script still running (installing packages). Waiting 30 seconds..."
        sleep 30
    done
    echo "Startup script completed!"
    
    # Ensure rsync is installed on remote instance
    echo "Checking for rsync on remote instance..."
    gcloud compute ssh $GCE_INSTANCE_NAME \
        --project=$PROJECT_ID \
        --zone=$GCE_ZONE \
        --command="command -v rsync >/dev/null 2>&1 || (sudo apt-get update && sudo apt-get install -y rsync)"
    
    # Create target directory
    gcloud compute ssh $GCE_INSTANCE_NAME \
        --project=$PROJECT_ID \
        --zone=$GCE_ZONE \
        --command="mkdir -p /opt/gujrat_tsr_agent"
    
    rsync -avz --progress \
        --exclude=".git/" \
        --exclude="venv/" \
        --exclude="output/" \
        --exclude="logs/" \
        --exclude="__pycache__/" \
        --exclude="*.pyc" \
        --exclude=".DS_Store" \
        -e "gcloud compute ssh $GCE_INSTANCE_NAME --project=$PROJECT_ID --zone=$GCE_ZONE --" \
        . :"/opt/gujrat_tsr_agent/"
    
    # Restart the service
    gcloud compute ssh $GCE_INSTANCE_NAME \
        --project=$PROJECT_ID \
        --zone=$GCE_ZONE \
        --command="cd /opt/gujrat_tsr_agent && source venv/bin/activate && pip install -r requirements.txt && sudo systemctl restart streamlit"
    
    echo -e "${GREEN}Deployment complete!${NC}"
}

# Function to view logs
view_logs() {
    echo -e "${YELLOW}Viewing application logs...${NC}"
    gcloud compute ssh $GCE_INSTANCE_NAME \
        --project=$PROJECT_ID \
        --zone=$GCE_ZONE \
        --command="sudo journalctl -u streamlit -f"
}

# Function to get instance IP
get_ip() {
    IP=$(gcloud compute instances describe $GCE_INSTANCE_NAME \
        --project=$PROJECT_ID \
        --zone=$GCE_ZONE \
        --format='get(networkInterfaces[0].accessConfigs[0].natIP)')
    echo -e "${GREEN}Instance IP: $IP${NC}"
    echo -e "Access your app at: ${GREEN}http://$IP:8501${NC}"
}

# Function to SSH into instance
ssh_instance() {
    echo -e "${YELLOW}Connecting to instance...${NC}"
    gcloud compute ssh $GCE_INSTANCE_NAME \
        --project=$PROJECT_ID \
        --zone=$GCE_ZONE
}

# Function to stop instance
stop_instance() {
    echo -e "${YELLOW}Stopping instance...${NC}"
    gcloud compute instances stop $GCE_INSTANCE_NAME \
        --project=$PROJECT_ID \
        --zone=$GCE_ZONE
    echo -e "${GREEN}Instance stopped${NC}"
}

# Function to start instance
start_instance() {
    echo -e "${YELLOW}Starting instance...${NC}"
    gcloud compute instances start $GCE_INSTANCE_NAME \
        --project=$PROJECT_ID \
        --zone=$GCE_ZONE
    echo -e "${GREEN}Instance started${NC}"
}

# Main menu
check_gcloud

echo "What would you like to do?"
echo "1) Create new instance"
echo "2) Deploy updates to existing instance"
echo "3) View logs"
echo "4) Get instance IP"
echo "5) SSH into instance"
echo "6) Stop instance"
echo "7) Start instance"
echo "8) Exit"
echo ""
read -p "Enter your choice [1-8]: " choice

case $choice in
    1)
        create_instance
        get_ip
        ;;
    2)
        deploy_updates
        ;;
    3)
        view_logs
        ;;
    4)
        get_ip
        ;;
    5)
        ssh_instance
        ;;
    6)
        stop_instance
        ;;
    7)
        start_instance
        ;;
    8)
        echo "Goodbye!"
        exit 0
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac
