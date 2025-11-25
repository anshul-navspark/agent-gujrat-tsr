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

# Clone or update repository (replace with your repo URL)
if [ -d "$APP_DIR/.git" ]; then
    echo "Updating existing repository..."
    cd $APP_DIR
    git pull
else
    echo "Cloning repository..."
    # Replace with your actual repository URL
    git clone https://github.com/anshul-navspark/agent-gujrat-tsr.git $APP_DIR
    cd $APP_DIR
fi

# Create virtual environment
python3 -m venv venv
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
