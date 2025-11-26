#!/bin/bash
# GCE Startup Script for Gujarat TSR Agent Streamlit App
# This script runs when the GCE instance starts

set -e

echo "Starting Gujarat TSR Agent deployment..."

# Update system packages
sudo apt-get update
sudo apt-get upgrade -y

# Install required system packages
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    git \
    rsync \
    chromium \
    chromium-driver \
    build-essential \
    libpoppler-cpp-dev \
    pkg-config \
    python3-dev \
    nginx \
    supervisor

# Set up application directory
APP_DIR="/opt/gujrat_tsr_agent"
sudo mkdir -p $APP_DIR
sudo chown -R $USER:$USER $APP_DIR

# Code will be deployed directly from local machine via gcloud scp
# Skipping git clone since repository is private
echo "Application directory ready. Code will be deployed separately..."
cd $APP_DIR

# Note: The actual code deployment happens via:
# gcloud compute scp --recurse . gujrat-tsr-agent:/opt/gujrat_tsr_agent/

# Create virtual environment
python3 -m venv venv

# The rest of the setup will happen after code deployment
# Check if code has been deployed (requirements.txt exists)
if [ -f "$APP_DIR/requirements.txt" ]; then
    echo "Code detected, completing setup..."
    source venv/bin/activate
    
    # Install Python dependencies
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # Set up environment variables
    # Create .env file if it doesn't exist
    if [ ! -f "$APP_DIR/.env" ]; then
        echo "Creating .env file..."
        cat > $APP_DIR/.env << 'EOF'
# Add your environment variables here
GEMINI_API_KEY=AIzaSyDx8TZgIr-ZkIDu51TrvfzzYYHAN6QUr1c
GEMINI_MODEL_NAME=gemini-2.5-flash
EOF
        echo "IMPORTANT: Please update $APP_DIR/.env with your actual API keys!"
    fi
    
    # Create necessary directories
    mkdir -p logs output/pdfs output/tsr
    
    # Set up Streamlit configuration
    mkdir -p ~/.streamlit
    cat > ~/.streamlit/config.toml << EOF
[server]
port = 8501
address = "0.0.0.0"
headless = true
enableCORS = false
enableXsrfProtection = true

[browser]
gatherUsageStats = false
serverAddress = "0.0.0.0"
serverPort = 8501
EOF
    
    # Copy systemd service file
    sudo cp deploy/streamlit.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable streamlit
    sudo systemctl restart streamlit
    
    # Set up nginx reverse proxy (optional, for HTTPS)
    if [ -f "deploy/nginx.conf" ]; then
        sudo cp deploy/nginx.conf /etc/nginx/sites-available/streamlit
        sudo ln -sf /etc/nginx/sites-available/streamlit /etc/nginx/sites-enabled/
        sudo nginx -t && sudo systemctl reload nginx
    fi
    
    echo "Deployment complete!"
    echo "Application is running on port 8501"
    echo "Access it at: http://$(curl -s ifconfig.me):8501"
    echo ""
    echo "To check status: sudo systemctl status streamlit"
    echo "To view logs: sudo journalctl -u streamlit -f"
else
    echo "Waiting for code deployment..."
    echo "After deploying code, run this script manually or use the deploy.sh script"
fi
