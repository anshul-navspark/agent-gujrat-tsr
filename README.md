---
title: Gujarat TSR Agent
emoji: 📄
colorFrom: blue
colorTo: green
sdk: streamlit
sdk_version: 1.41.0
app_file: app/streamlit_app_cloud.py
pinned: false
---

# Gujarat TSR Agent

A comprehensive automation solution for fetching land records from the Gujarat AnyRoR portal and generating Title Search Reports (TSR) using AI-powered document processing.

## 🚀 Features

- **Land Record Scraping**: Automated fetching of land records from the Gujarat AnyRoR website
- **AI-Powered CAPTCHA Solving**: Uses Google Gemini AI to solve CAPTCHAs
- **TSR Generation**: Generates professional Title Search Reports from land record PDFs
- **Optimized Extraction**: Single LLM call for 60% faster processing with identical accuracy
- **Batch Processing**: Process multiple records from Excel files with parallel execution
- **Multi-Language Support**: English to Gujarati translation for form inputs
- **Multi-Client Support**: Save lender/client details in `clients.json` and pick the active client from a sidebar dropdown. The Streamlit UI plumbs the selection through the API into the DOCX template.
- **Cloud Deployment**: Deployable on Google Cloud Run for serverless operation
- **Streamlit UI**: User-friendly web interface for record processing
- **GCS Caching**: Cache fetched records in Google Cloud Storage to avoid re-fetching for 1 week

---

## 📁 Project Structure

```
gujrat_tsr_agent/
├── core/                      # Core domain models and interfaces
│   ├── models.py              # Domain models (LandRecordRequest, APIResponse)
│   ├── interfaces.py          # Service interfaces
│   ├── config.py              # Centralized configuration management
│   └── exceptions.py          # Custom exception hierarchy
│
├── services/                  # Business logic services
│   ├── translation_service.py # English-Gujarati translation
│   ├── file_service.py        # File operations (ZIP, temp files)
│   ├── scraping_service.py    # Web scraping abstraction
│   ├── cache_service.py       # GCS caching for fetched records
│   └── processing_service.py  # TSR processing coordination
│
├── app/                       # Streamlit application
│   ├── streamlit_app_cloud.py # Main Streamlit entry point
│   ├── api_client.py          # API client for backend communication
│   ├── components/            # UI components
│   └── services/              # Streamlit-specific services
│
├── anyror/                    # AnyRoR scraping module
│   ├── captcha_solver.py      # AI CAPTCHA solving
│   ├── webdriver_manager.py   # Selenium WebDriver management
│   └── scraper.py             # Main scraping logic
│
├── tsr_generator/             # TSR document generation
│   ├── extractors/            # PDF data extraction (unified_extractor.py)
│   ├── document/              # DOCX generation
│   └── processors/            # Data processing
│
├── api/                       # FastAPI backend
│   ├── server.py              # FastAPI server
│   ├── dependencies.py        # Dependency injection
│   └── middleware.py          # Custom middleware
│
├── tests/                     # Test suite
├── Dockerfile                 # Container configuration
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

---

## 🛠️ Installation

### Prerequisites

- Python 3.11+
- Google Chrome (for web scraping)
- Google Gemini API key

### Local Setup

```bash
# Clone the repository
git clone <repository-url>
cd gujrat_tsr_agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
echo "GEMINI_API_KEY=your_key_here" > .env
echo "USE_OPTIMIZED_EXTRACTION=true" >> .env
```

---

## 🚀 Usage

### Run the API Server

```bash
uvicorn api.server:app --host 0.0.0.0 --port 8080
```

### Run the Streamlit UI

```bash
streamlit run app/streamlit_app_cloud.py
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/generate-tsr` | POST | Generate TSR from uploaded PDF |
| `/process-record` | POST | Scrape and generate TSR from record details (with caching) |
| `/cache-stats` | GET | Get cache statistics |
| `/debug-env` | GET | Debug environment configuration |

**Example: Generate TSR from PDF**
```bash
curl -X POST "http://localhost:8080/generate-tsr" \
  -F "file=@/path/to/document.pdf" \
  --output result.docx
```

**Example: Process Record**
```bash
curl -X POST "http://localhost:8080/process-record" \
  -H "Content-Type: application/json" \
  -d '{"district": "Kutch", "taluka": "Abdasa", "village": "Trambo", "survey_number": "150"}'
```

---

## 🐳 Docker Deployment

### Build and Run Locally

```bash
# Build the Docker image
docker build -t agent-gujrat-tsr .

# Run the container
docker run -p 8080:8080 -e GEMINI_API_KEY=your_key agent-gujrat-tsr
```

### Deploy to Google Cloud Run

```bash
# Set your project
gcloud config set project YOUR_PROJECT_ID

# Build and push (uses cloud builder, no local Docker needed)
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/agent-gujrat-tsr

# Deploy
gcloud run deploy agent-gujrat-tsr \
  --image gcr.io/YOUR_PROJECT_ID/agent-gujrat-tsr \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=your_key
```

---

## ☁️ Streamlit Cloud Deployment

1. Push your code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Create a new app pointing to `app/streamlit_app_cloud.py`
4. Add secrets in the dashboard:
   ```toml
   GEMINI_API_KEY = "your_key"
   API_URL = "https://your-cloud-run-url.run.app"
   ```

---

## ⚡ Optimized Extraction

The optimized extraction pipeline reduces API calls from 3 to 1, achieving:
- **60% faster** processing time
- **66% fewer** API calls
- **Identical** accuracy to the original method

Enable via environment variable:
```bash
USE_OPTIMIZED_EXTRACTION=true
GEMINI_MODEL_NAME=gemini-2.5-flash
```

---

## 👥 Multi-Client TSRs

The application supports generating TSRs for multiple clients (lenders / borrowers / counterparties).

### How it works

1. A `clients.json` file at the repo root holds saved client details:
   - `client_name`, `client_cin`, `client_address`, `kind_attn`, `ref_prefix`, `reference_email_date`
2. The Streamlit sidebar has an **Active Client** dropdown listing every entry by `display_name`.
3. The selected client flows through the API into the generated DOCX (the "To:" block and the "Ref. No." prefix both update).
4. The GCS cache is split: scraped PDFs are shared across clients, generated DOCXs are stored per-client. Two clients running the same survey get distinct DOCXs.

### Adding a client

Edit `clients.json`, add an entry like:

```json
{
  "id": "my_new_client",
  "display_name": "My New Client",
  "client_name": "My New Client Pvt Ltd",
  "client_cin": "(CIN: ...),",
  "client_address": "Address line 1,\nAddress line 2.",
  "kind_attn": "Kind Attn.: Mr. Foo",
  "ref_prefix": "MNC",
  "reference_email_date": "DD.MM.YYYY"
}
```

Then commit and redeploy. The new client appears in the sidebar dropdown.

---

## 📦 GCS Caching

The application supports caching fetched records in Google Cloud Storage to avoid unnecessary re-fetching from the AnyRoR portal.

### How It Works

1. When a record is requested, the API first checks if it exists in the cache
2. If cached and not expired (within the last 7 days), the cached version is returned
3. If not cached or expired, the record is fetched from AnyRoR and stored in the cache
4. Response headers indicate cache status: `X-Cache-Status: HIT` or `X-Cache-Status: MISS`

### Configuration

Set the following environment variable to enable caching:

```bash
# Required: GCS bucket name for storing cache
GCS_CACHE_BUCKET=your-gcs-bucket-name
```

### Cache TTL

By default, cached records expire after **7 days**. After expiration, the record will be re-fetched and re-cached.

### Cache Structure in GCS

```
your-bucket/
├── cache/
│   ├── {cache_key_1}/
│   │   ├── metadata.json    # Timestamp, request info
│   │   ├── original.pdf     # Scraped PDF
│   │   └── tsr.docx         # Generated TSR
│   ├── {cache_key_2}/
│   │   └── ...
```

### Check Cache Stats

```bash
curl http://localhost:8080/cache-stats
```

Returns:
```json
{
  "status": "enabled",
  "total_cached_records": 42,
  "total_files": 126,
  "total_size_mb": 15.6,
  "ttl_days": 7
}
```

### Cloud Run Deployment with Caching

```bash
gcloud run deploy agent-gujrat-tsr \
  --image gcr.io/YOUR_PROJECT_ID/agent-gujrat-tsr \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=your_key,GCS_CACHE_BUCKET=your-cache-bucket
```

Make sure the Cloud Run service account has access to the GCS bucket.

---

## 📝 Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | Required |
| `USE_OPTIMIZED_EXTRACTION` | Enable optimized pipeline | `true` |
| `GEMINI_MODEL_NAME` | LLM model to use | `gemini-2.5-flash` |
| `HEADLESS` | Run browser in headless mode | `true` |
| `MAX_WORKERS` | Parallel processing workers | `20` |
| `GCS_CACHE_BUCKET` | GCS bucket for caching | Optional |

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html
```

---

## 🏗️ Architecture

The application follows a layered architecture with SOLID principles:

```
┌───────────────────────────────────────────────────────────┐
│                   PRESENTATION LAYER                      │
│     Streamlit App  ◄──────────►  FastAPI Server           │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│                     SERVICE LAYER                         │
│  TranslationService │ FileService │ ScrapingService │     │
│                     CacheService (GCS)                    │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│                      CORE LAYER                           │
│      Models  │  Interfaces  │  Config  │  Exceptions      │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE LAYER                     │
│     AnyRoR Scraper  │  TSR Generator  │  Utilities        │
└───────────────────────────────────────────────────────────┘
```

---

## 📄 License

This project is licensed under the MIT License.

## ⚠️ Disclaimer

This tool is for educational and personal use only. Please ensure you comply with the terms of service of the AnyRoR website.
