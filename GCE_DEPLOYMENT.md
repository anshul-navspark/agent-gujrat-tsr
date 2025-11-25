# Deploying Gujarat TSR Agent to Google Compute Engine (GCE)

This guide walks you through deploying your Streamlit application to Google Compute Engine.

## Prerequisites

1. **Google Cloud Account** with billing enabled
2. **gcloud CLI** installed ([Installation Guide](https://cloud.google.com/sdk/docs/install))
3. **Git repository** for your code (GitHub, GitLab, etc.)
4. **API Keys** (Gemini API key)

## Quick Start

### Option 1: Automated Deployment (Recommended)

1. **Configure the deployment script:**
   ```bash
   # Edit deploy/deploy.sh and update these variables:
   GCE_INSTANCE_NAME="gujrat-tsr-agent"
   GCE_ZONE="us-central1-a"
   PROJECT_ID="your-project-id"
   ```

2. **Make scripts executable:**
   ```bash
   chmod +x deploy/deploy.sh
   chmod +x deploy/gce_startup.sh
   ```

3. **Run the deployment:**
   ```bash
   ./deploy/deploy.sh
   # Select option 1 to create a new instance
   ```

4. **Wait for deployment** (5-10 minutes for initial setup)

5. **Access your app:**
   ```bash
   ./deploy/deploy.sh
   # Select option 4 to get the instance IP
   # Then visit http://YOUR_IP:8501
   ```

### Option 2: Manual Deployment

#### Step 1: Create a GCE Instance

```bash
# Set your project
gcloud config set project YOUR_PROJECT_ID

# Create the instance
gcloud compute instances create gujrat-tsr-agent \
    --zone=us-central1-a \
    --machine-type=e2-standard-2 \
    --boot-disk-size=30GB \
    --boot-disk-type=pd-standard \
    --image-family=debian-11 \
    --image-project=debian-cloud \
    --tags=http-server,https-server \
    --scopes=cloud-platform
```

#### Step 2: Configure Firewall Rules

```bash
# Allow HTTP traffic on port 8501
gcloud compute firewall-rules create allow-streamlit \
    --allow=tcp:8501 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=http-server \
    --description="Allow Streamlit traffic"

# Optional: Allow HTTPS
gcloud compute firewall-rules create allow-https \
    --allow=tcp:443 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=https-server
```

#### Step 3: SSH into the Instance

```bash
gcloud compute ssh gujrat-tsr-agent --zone=us-central1-a
```

#### Step 4: Install Dependencies

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install required packages
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    git \
    chromium \
    chromium-driver \
    build-essential \
    libpoppler-cpp-dev \
    pkg-config \
    python3-dev
```

#### Step 5: Clone and Setup Application

```bash
# Create application directory
sudo mkdir -p /opt/gujrat_tsr_agent
sudo chown -R $USER:$USER /opt/gujrat_tsr_agent

# Clone your repository
cd /opt/gujrat_tsr_agent
git clone YOUR_REPO_URL .

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

#### Step 6: Configure Environment Variables

```bash
# Create .env file
nano /opt/gujrat_tsr_agent/.env
```

Add your environment variables:
```env
GEMINI_API_KEY=your_actual_api_key_here
GEMINI_MODEL_NAME=gemini-2.5-flash
```

#### Step 7: Setup Systemd Service

```bash
# Copy service file
sudo cp deploy/streamlit.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start the service
sudo systemctl enable streamlit
sudo systemctl start streamlit

# Check status
sudo systemctl status streamlit
```

#### Step 8: Access Your Application

```bash
# Get your instance's external IP
gcloud compute instances describe gujrat-tsr-agent \
    --zone=us-central1-a \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)'

# Visit http://YOUR_IP:8501 in your browser
```

## Configuration

### Machine Types

Choose based on your workload:

- **e2-micro** ($6/month) - Testing only, very limited
- **e2-small** ($12/month) - Light usage
- **e2-medium** ($24/month) - Moderate usage
- **e2-standard-2** ($48/month) - **Recommended** for production
- **e2-standard-4** ($96/month) - Heavy usage

### Disk Size

- **20GB** - Minimum
- **30GB** - **Recommended**
- **50GB+** - If storing many PDFs/TSRs

## Optional: Setup HTTPS with Nginx

### 1. Install Nginx

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

### 2. Configure Nginx

```bash
# Copy nginx configuration
sudo cp deploy/nginx.conf /etc/nginx/sites-available/streamlit

# Update with your domain
sudo nano /etc/nginx/sites-available/streamlit
# Replace 'your-domain.com' with your actual domain

# Enable site
sudo ln -s /etc/nginx/sites-available/streamlit /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. Get SSL Certificate

```bash
sudo certbot --nginx -d your-domain.com
```

## Maintenance

### View Logs

```bash
# Using deployment script
./deploy/deploy.sh  # Select option 3

# Or manually
sudo journalctl -u streamlit -f
```

### Deploy Updates

```bash
# Using deployment script
./deploy/deploy.sh  # Select option 2

# Or manually
cd /opt/gujrat_tsr_agent
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart streamlit
```

### Restart Service

```bash
sudo systemctl restart streamlit
```

### Stop/Start Instance

```bash
# Stop (to save costs when not in use)
gcloud compute instances stop gujrat-tsr-agent --zone=us-central1-a

# Start
gcloud compute instances start gujrat-tsr-agent --zone=us-central1-a
```

## Troubleshooting

### Service Won't Start

```bash
# Check service status
sudo systemctl status streamlit

# Check logs
sudo journalctl -u streamlit -n 100 --no-pager

# Check if port is in use
sudo netstat -tlnp | grep 8501
```

### ChromeDriver Issues

```bash
# Verify chromium is installed
which chromium

# Verify chromium-driver is installed
which chromedriver

# Check versions
chromium --version
chromedriver --version
```

### Permission Issues

```bash
# Fix ownership
sudo chown -R www-data:www-data /opt/gujrat_tsr_agent

# Fix permissions
sudo chmod -R 755 /opt/gujrat_tsr_agent
```

### Out of Memory

```bash
# Check memory usage
free -h

# Consider upgrading to a larger machine type
gcloud compute instances stop gujrat-tsr-agent --zone=us-central1-a
gcloud compute instances set-machine-type gujrat-tsr-agent \
    --machine-type=e2-standard-4 \
    --zone=us-central1-a
gcloud compute instances start gujrat-tsr-agent --zone=us-central1-a
```

## Cost Optimization

### 1. Use Preemptible Instances (70% cheaper)

```bash
# Add --preemptible flag when creating instance
gcloud compute instances create gujrat-tsr-agent \
    --preemptible \
    # ... other flags
```

**Note:** Preemptible instances can be terminated at any time.

### 2. Stop Instance When Not in Use

```bash
# Stop instance
gcloud compute instances stop gujrat-tsr-agent --zone=us-central1-a

# You only pay for disk storage when stopped (~$1.60/month for 30GB)
```

### 3. Use Committed Use Discounts

For long-term usage, commit to 1 or 3 years for up to 57% discount.

## Security Best Practices

1. **Restrict firewall rules** to specific IP ranges if possible
2. **Use HTTPS** with SSL certificate
3. **Keep system updated:**
   ```bash
   sudo apt-get update && sudo apt-get upgrade -y
   ```
4. **Use secrets management** instead of .env file:
   ```bash
   # Use Google Secret Manager
   gcloud secrets create gemini-api-key --data-file=-
   ```
5. **Enable OS Login** for better SSH security
6. **Regular backups** of your data

## Monitoring

### Setup Cloud Monitoring

```bash
# Install monitoring agent
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
sudo bash add-google-cloud-ops-agent-repo.sh --also-install
```

### View Metrics in Console

Visit: https://console.cloud.google.com/monitoring

## Useful Commands

```bash
# SSH into instance
gcloud compute ssh gujrat-tsr-agent --zone=us-central1-a

# Copy files to instance
gcloud compute scp local-file.txt gujrat-tsr-agent:/opt/gujrat_tsr_agent/ --zone=us-central1-a

# Copy files from instance
gcloud compute scp gujrat-tsr-agent:/opt/gujrat_tsr_agent/logs/app.log . --zone=us-central1-a

# Get instance info
gcloud compute instances describe gujrat-tsr-agent --zone=us-central1-a

# List all instances
gcloud compute instances list
```

## Support

For issues specific to:
- **GCP/GCE:** [Google Cloud Support](https://cloud.google.com/support)
- **Streamlit:** [Streamlit Documentation](https://docs.streamlit.io/)
- **This Application:** Check logs and GitHub issues

## Next Steps

1. ✅ Deploy to GCE
2. ⬜ Setup custom domain
3. ⬜ Configure HTTPS
4. ⬜ Setup monitoring and alerts
5. ⬜ Configure automated backups
6. ⬜ Implement CI/CD pipeline
