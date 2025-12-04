# Automatic GEMINI_API_KEY Loading - Quick Reference

## What Changed

The deployment script now **automatically loads** `GEMINI_API_KEY` from your `.env` file, so you don't need to manually export it before every deployment.

---

## How It Works

### Before (Manual):
```bash
# You had to do this every time:
export GEMINI_API_KEY='AIzaSyDN5wuJQcO-2IBW0BulR57xtKayeIj-vrs'
cd deploy
./deploy_cloud_run.sh
```

### After (Automatic):
```bash
# Just run the deployment script:
cd deploy
./deploy_cloud_run.sh
# Script automatically loads GEMINI_API_KEY from ../.env
```

---

## Deployment Process

The script now follows these steps:

1. **Step 0**: Load environment variables from `.env` file
   - Looks for `.env` in parent directory
   - Extracts `GEMINI_API_KEY`
   - Exports it for use in deployment

2. **Step 1**: Build Docker image

3. **Step 2**: Deploy to Cloud Run
   - Verifies `GEMINI_API_KEY` is set
   - Shows first 20 characters for confirmation
   - Sets environment variables in Cloud Run

---

## Your .env File

Make sure your `.env` file contains:

```bash
GEMINI_API_KEY=AIzaSyDN5wuJQcO-2IBW0BulR57xtKayeIj-vrs
```

**Location**: `/Users/anshulgoyal/work/gujrat_tsr_agent/.env`

✅ **Already configured** - Your `.env` file already has the API key!

---

## Deployment Command

Simply run:

```bash
cd /Users/anshulgoyal/work/gujrat_tsr_agent/deploy
./deploy_cloud_run.sh
```

The script will:
- ✅ Automatically load `GEMINI_API_KEY` from `.env`
- ✅ Build the Docker image
- ✅ Deploy to Cloud Run with all environment variables
- ✅ Show confirmation that API key is loaded

---

## What You'll See

```bash
=== Deploying to Cloud Run ===
Project: neon-alcove-479309-q3
Service: gujrat-tsr-agent
Region: asia-south1

Step 0: Loading environment variables from .env file...
✅ Found .env file
✅ Loaded GEMINI_API_KEY from .env file

Step 1: Building container image...
Build timestamp: 1 (forces fresh build)
...

Step 2: Deploying to Cloud Run...
✅ GEMINI_API_KEY is set (AIzaSyDN5wuJQcO-2IBW...)

Deploying...
```

---

## Error Handling

If `GEMINI_API_KEY` is not found, you'll see:

```bash
❌ ERROR: GEMINI_API_KEY is not set!

Please add it to your .env file:
  echo 'GEMINI_API_KEY=your-api-key-here' >> .env

Or export it manually:
  export GEMINI_API_KEY='your-api-key-here'
```

---

## Benefits

1. **No Manual Export**: Don't need to remember to export the API key
2. **Consistent**: Same key used every time from `.env`
3. **Secure**: API key stays in `.env` file (not in shell history)
4. **Convenient**: One command to deploy

---

## Files Modified

- **`deploy/deploy_cloud_run.sh`**:
  - Added automatic `.env` file loading
  - Improved error messages
  - Shows API key confirmation (first 20 chars)

---

## Ready to Deploy!

Your deployment is now simplified:

```bash
cd deploy
./deploy_cloud_run.sh
```

That's it! No manual exports needed. 🎉
