# MCP Server Deployment Guide

Complete guide for deploying the TSR Tools MCP Server in various environments.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [Production Deployment](#production-deployment)
4. [Cloud Deployment](#cloud-deployment)
5. [Configuration](#configuration)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

- **Python**: 3.11 or higher
- **Chrome/Chromium**: Latest version (for PDF fetching)
- **RAM**: 4GB minimum, 8GB recommended
- **Disk**: 2GB free space
- **Network**: Internet access to Gujarat government website

### Required API Keys

1. **Google Gemini API Key**
   - Sign up at: https://makersuite.google.com/app/apikey
   - Free tier available (60 requests/minute)
   - Required for AI-powered PDF extraction

### Optional Requirements

- **Git**: For cloning the repository
- **Virtual Environment**: Recommended for isolation

---

## Local Development Setup

### Step 1: Clone the Repository

```bash
git clone https://github.com/risjainucd/agent-gujrat-tsr.git
cd agent-gujrat-tsr
```

### Step 2: Create Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
# Install main project dependencies
pip install -r requirements.txt

# Install MCP server dependencies
pip install -r mcp_server/requirements.txt
```

### Step 4: Set Environment Variables

Create a `.env` file in the project root:

```bash
# .env
GOOGLE_API_KEY=your_actual_api_key_here
```

Or export directly:

```bash
export GOOGLE_API_KEY="your_actual_api_key_here"
```

### Step 5: Verify Chrome Installation

```bash
# Check Chrome version
google-chrome --version
# or
chromium --version

# If not installed (Ubuntu/Debian)
sudo apt update
sudo apt install -y chromium-browser

# If not installed (Mac)
brew install --cask google-chrome

# If not installed (Windows)
# Download from: https://www.google.com/chrome/
```

### Step 6: Test the Installation

```bash
# Run simple validation test
python mcp_server/test_mcp_simple.py

# You should see:
# ✓ All tests passed! MCP server structure is valid.
```

### Step 7: Test Individual Tools

```bash
# Test with your data (requires internet)
python mcp_server/tools/fetch_pdf.py \
  --district "Kachchh" \
  --taluka "Andasa" \
  --village "Trambo" \
  --survey-number "149"

# If successful, you'll get a PDF in output/pdfs/
```

---

## Production Deployment

### Option 1: Systemd Service (Linux)

Create a systemd service for the MCP server:

```bash
# Create service file
sudo nano /etc/systemd/system/tsr-mcp-server.service
```

Add the following content:

```ini
[Unit]
Description=TSR Tools MCP Server
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/agent-gujrat-tsr
Environment="GOOGLE_API_KEY=your_api_key_here"
Environment="PYTHONPATH=/path/to/agent-gujrat-tsr"
ExecStart=/path/to/venv/bin/python /path/to/agent-gujrat-tsr/mcp_server/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable tsr-mcp-server

# Start service
sudo systemctl start tsr-mcp-server

# Check status
sudo systemctl status tsr-mcp-server

# View logs
sudo journalctl -u tsr-mcp-server -f
```

### Option 2: Docker Deployment

Create `Dockerfile` in `mcp_server/`:

```dockerfile
FROM python:3.11-slim

# Install Chrome
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt /app/
COPY mcp_server/requirements.txt /app/mcp_server/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r mcp_server/requirements.txt

# Copy application
COPY . /app/

# Set environment
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose port (if needed for HTTP interface)
# EXPOSE 8080

# Run server
CMD ["python", "mcp_server/server.py"]
```

Build and run:

```bash
# Build image
docker build -t tsr-mcp-server .

# Run container
docker run -d \
  --name tsr-mcp-server \
  -e GOOGLE_API_KEY=your_api_key \
  -v $(pwd)/output:/app/output \
  tsr-mcp-server

# View logs
docker logs -f tsr-mcp-server

# Stop container
docker stop tsr-mcp-server
```

### Option 3: Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  mcp-server:
    build: .
    container_name: tsr-mcp-server
    environment:
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - PYTHONPATH=/app
    volumes:
      - ./output:/app/output
      - ./mcp_server:/app/mcp_server
    restart: unless-stopped
```

Run with:

```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

---

## Cloud Deployment

### Google Cloud Platform (GCP)

#### Option A: Cloud Run

```bash
# 1. Build and push to Container Registry
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/tsr-mcp-server

# 2. Deploy to Cloud Run
gcloud run deploy tsr-mcp-server \
  --image gcr.io/YOUR_PROJECT_ID/tsr-mcp-server \
  --platform managed \
  --region us-central1 \
  --memory 2Gi \
  --timeout 300 \
  --set-env-vars GOOGLE_API_KEY=your_api_key

# 3. Test
curl https://tsr-mcp-server-xxxx-uc.a.run.app
```

#### Option B: Compute Engine

```bash
# 1. Create instance
gcloud compute instances create tsr-mcp-server \
  --machine-type e2-medium \
  --image-family ubuntu-2204-lts \
  --image-project ubuntu-os-cloud \
  --boot-disk-size 20GB

# 2. SSH into instance
gcloud compute ssh tsr-mcp-server

# 3. Install dependencies and setup (follow Local Setup steps)

# 4. Setup systemd service (see Production Deployment)
```

### AWS Deployment

#### Option A: EC2

```bash
# 1. Launch EC2 instance (Ubuntu 22.04, t2.medium)

# 2. SSH into instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# 3. Install dependencies
sudo apt update
sudo apt install -y python3-pip git chromium-browser

# 4. Clone and setup (follow Local Setup steps)

# 5. Setup systemd service
```

#### Option B: ECS (Fargate)

Create `task-definition.json`:

```json
{
  "family": "tsr-mcp-server",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "tsr-mcp-server",
      "image": "your-ecr-repo/tsr-mcp-server:latest",
      "environment": [
        {
          "name": "GOOGLE_API_KEY",
          "value": "your_api_key"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/tsr-mcp-server",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

Deploy:

```bash
# Register task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json

# Create service
aws ecs create-service \
  --cluster your-cluster \
  --service-name tsr-mcp-server \
  --task-definition tsr-mcp-server \
  --desired-count 1 \
  --launch-type FARGATE
```

### Azure Deployment

#### Container Instances

```bash
# 1. Create resource group
az group create --name tsr-rg --location eastus

# 2. Build and push to ACR
az acr build --registry yourregistry \
  --image tsr-mcp-server:latest .

# 3. Deploy container
az container create \
  --resource-group tsr-rg \
  --name tsr-mcp-server \
  --image yourregistry.azurecr.io/tsr-mcp-server:latest \
  --cpu 1 \
  --memory 2 \
  --environment-variables GOOGLE_API_KEY=your_api_key
```

---

## Configuration

### Environment Variables

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `GOOGLE_API_KEY` | Yes | Google Gemini API key | None |
| `PYTHONPATH` | Yes | Path to project root | Current dir |
| `OUTPUT_DIR` | No | Base output directory | `output` |
| `MAX_WORKERS` | No | Max parallel workers | `3` |
| `HEADLESS` | No | Run Chrome headless | `true` |

### MCP Server Configuration

Edit `mcp_server/config.json`:

```json
{
  "mcpServers": {
    "tsr-tools": {
      "command": "python",
      "args": ["/absolute/path/to/agent-gujrat-tsr/mcp_server/server.py"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/agent-gujrat-tsr",
        "GOOGLE_API_KEY": "your_api_key"
      }
    }
  }
}
```

### Logging Configuration

Adjust logging levels in tools if needed:

```python
# In any tool file
import logging
logging.basicConfig(level=logging.INFO)  # Change to DEBUG for verbose logs
```

---

## Troubleshooting

### Issue 1: Chrome/ChromeDriver Mismatch

**Symptom**: `chromedriver version might not be compatible`

**Solution**:
```bash
# Remove existing chromedriver
sudo rm -f /usr/bin/chromedriver

# Install webdriver-manager (already in requirements)
pip install --upgrade webdriver-manager

# The tool will auto-download correct version
```

### Issue 2: Network Connection Failed

**Symptom**: `ERR_TUNNEL_CONNECTION_FAILED`

**Solutions**:
1. Check internet connectivity
2. Verify no proxy blocking
3. Test Gujarat website directly: https://anyror.gujarat.gov.in

### Issue 3: API Key Issues

**Symptom**: `Authentication failed` or `PERMISSION_DENIED`

**Solutions**:
```bash
# Verify API key is set
echo $GOOGLE_API_KEY

# Test API key
curl -H "Content-Type: application/json" \
  -d '{"contents":[{"parts":[{"text":"test"}]}]}' \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key=$GOOGLE_API_KEY"
```

### Issue 4: Module Import Errors

**Symptom**: `ModuleNotFoundError`

**Solutions**:
```bash
# Ensure PYTHONPATH is set
export PYTHONPATH=/path/to/agent-gujrat-tsr:$PYTHONPATH

# Or install in development mode
pip install -e .

# Verify imports
python -c "from services.processing_service import LandRecordProcessor"
```

### Issue 5: Permission Denied

**Symptom**: `Permission denied` when writing files

**Solutions**:
```bash
# Check output directory permissions
ls -la output/

# Fix permissions
sudo chown -R $USER:$USER output/
chmod -R 755 output/
```

### Issue 6: Memory Issues

**Symptom**: Process killed or OOM errors

**Solutions**:
1. Reduce `max_workers` in batch processing
2. Increase system memory
3. Process in smaller batches
4. Monitor memory: `htop` or `top`

### Issue 7: Timeout Errors

**Symptom**: PDF fetch times out

**Solutions**:
```python
# Increase timeout in anyror_refactored.py (if needed)
# Or retry with --regenerate flag
python mcp_server/tools/fetch_pdf.py ... --regenerate
```

---

## Performance Optimization

### 1. Parallel Processing

```bash
# Increase workers for batch processing
python mcp_server/tools/batch_process.py data.xlsx --workers 5
```

### 2. Caching

PDFs are automatically cached. To regenerate:

```bash
python mcp_server/tools/fetch_pdf.py ... --regenerate
```

### 3. Headless Mode

Always use headless mode in production:

```bash
# Already default, but ensure:
python mcp_server/tools/fetch_pdf.py ... --headless
```

### 4. Resource Limits

For Docker:

```bash
docker run -d \
  --cpus="2" \
  --memory="4g" \
  -e GOOGLE_API_KEY=key \
  tsr-mcp-server
```

---

## Monitoring

### Health Checks

Create a simple health check:

```bash
# Check if server is responsive
python -c "import sys; sys.path.insert(0, 'mcp_server'); from tools import fetch_pdf; print('OK')"
```

### Logging

Monitor logs:

```bash
# Systemd
sudo journalctl -u tsr-mcp-server -f

# Docker
docker logs -f tsr-mcp-server

# File-based (configure in code)
tail -f /var/log/tsr-mcp-server.log
```

### Metrics

Monitor key metrics:
- PDF fetch success rate
- TSR generation time
- Memory usage
- Disk space (output directory)

---

## Security Best Practices

### 1. API Key Management

```bash
# Never commit API keys to Git
echo ".env" >> .gitignore

# Use secret management
# AWS: AWS Secrets Manager
# GCP: Secret Manager
# Azure: Key Vault
```

### 2. Network Security

- Run MCP server in private network
- Use firewall rules to restrict access
- Enable HTTPS if exposing HTTP interface

### 3. File Permissions

```bash
# Restrict output directory
chmod 700 output/

# Run as non-root user
useradd -m -s /bin/bash tsr-user
su - tsr-user
```

### 4. Input Validation

All tools validate inputs before processing. Don't bypass validation.

---

## Backup and Recovery

### Backup Strategy

```bash
# Backup output directory
tar -czf tsr-backup-$(date +%Y%m%d).tar.gz output/

# Backup to cloud
aws s3 cp output/ s3://your-bucket/backups/ --recursive
```

### Recovery

```bash
# Restore from backup
tar -xzf tsr-backup-20251203.tar.gz

# Verify
ls -la output/
```

---

## Scaling

### Horizontal Scaling

Run multiple instances:

```bash
# Instance 1 (workers 1-3)
MAX_WORKERS=3 python mcp_server/server.py

# Instance 2 (workers 4-6)
MAX_WORKERS=3 python mcp_server/server.py
```

### Load Balancing

Use nginx or cloud load balancers to distribute requests.

---

## Support

For issues:
1. Check [Troubleshooting](#troubleshooting)
2. Review logs
3. Test individual tools
4. Open GitHub issue with details

---

## Update Instructions

```bash
# Pull latest changes
git pull origin main

# Update dependencies
pip install --upgrade -r requirements.txt
pip install --upgrade -r mcp_server/requirements.txt

# Restart service
sudo systemctl restart tsr-mcp-server
```

---

## Checklist for Production

- [ ] Python 3.11+ installed
- [ ] Chrome/Chromium installed
- [ ] API keys configured
- [ ] Virtual environment created
- [ ] Dependencies installed
- [ ] Tests passing
- [ ] Environment variables set
- [ ] Service configured (systemd/docker)
- [ ] Logging configured
- [ ] Monitoring setup
- [ ] Backups configured
- [ ] Security hardened
- [ ] Documentation reviewed

---

**Deployment Status**: Production-ready ✅

**Last Updated**: December 3, 2025
