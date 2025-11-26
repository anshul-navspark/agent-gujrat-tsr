# Deployment Steps for Gujarat TSR Agent on GCE

## Current Status
- ✅ GCE instance created and running at `34.93.77.97`
- ✅ System packages installed (Python, Chrome, nginx, etc.)
- ❌ Application code not deployed yet
- ❌ Firewall rule for port 8501 not created yet

## Steps to Complete Deployment

### 1. Create Firewall Rule (One-time setup)
```bash
gcloud compute firewall-rules create allow-streamlit \
    --project=neon-alcove-479309-q3 \
    --allow=tcp:8501 \
    --source-ranges=0.0.0.0/0 \
    --description="Allow Streamlit traffic on port 8501"
```

### 2. Deploy Code to Instance
From your local project directory:
```bash
gcloud compute scp --recurse \
    --project=neon-alcove-479309-q3 \
    --zone=asia-south1-a \
    . gujrat-tsr-agent:/opt/gujrat_tsr_agent/ \
    --exclude=".git/*" \
    --exclude="venv/*" \
    --exclude="output/*" \
    --exclude="logs/*" \
    --exclude="__pycache__/*"
```

### 3. Complete Setup on Instance
SSH into the instance and run the setup:
```bash
# SSH into instance
gcloud compute ssh gujrat-tsr-agent \
    --project=neon-alcove-479309-q3 \
    --zone=asia-south1-a

# Once inside, run the startup script to complete setup
cd /opt/gujrat_tsr_agent
sudo bash deploy/gce_startup.sh
```

### 4. Verify Deployment
```bash
# Check if Streamlit service is running
sudo systemctl status streamlit

# View logs
sudo journalctl -u streamlit -f
```

### 5. Access Your Application
Open in browser: `http://34.93.77.97:8501`

---

## Alternative: Use deploy.sh Script

The `deploy/deploy.sh` script provides a menu-driven interface:

```bash
./deploy/deploy.sh
```

Choose option 2: "Deploy updates to existing instance"

---

## Troubleshooting

### If Streamlit service fails to start:
```bash
# Check logs
sudo journalctl -u streamlit -n 50

# Restart service
sudo systemctl restart streamlit
```

### If port 8501 is not accessible:
```bash
# Verify firewall rule exists
gcloud compute firewall-rules list --project=neon-alcove-479309-q3

# Check if Streamlit is listening
sudo netstat -tlnp | grep 8501
```

### To update code after initial deployment:
```bash
# Just run deploy.sh and choose option 2
./deploy/deploy.sh
```
