# Gujarat TSR Agent

A comprehensive automation solution for fetching land records from the Gujarat AnyRoR portal and generating Title Search Reports (TSR) using AI-powered document processing.

## 🚀 Features

- **Land Record Scraping**: Automated fetching of land records from the Gujarat AnyRoR website
- **AI-Powered CAPTCHA Solving**: Uses Google Gemini AI to solve CAPTCHAs
- **TSR Generation**: Generates professional Title Search Reports from land record PDFs
- **Optimized Extraction**: Single LLM call for 60% faster processing with identical accuracy
- **Batch Processing**: Process multiple records from Excel files with parallel execution
- **Multi-Language Support**: English to Gujarati translation for form inputs
- **Cloud Deployment**: Deployable on Google Cloud Run for serverless operation
- **Streamlit UI**: User-friendly web interface for record processing

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
| `/process-record` | POST | Scrape and generate TSR from record details |

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

## 📝 Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | Required |
| `USE_OPTIMIZED_EXTRACTION` | Enable optimized pipeline | `true` |
| `GEMINI_MODEL_NAME` | LLM model to use | `gemini-2.5-flash` |
| `HEADLESS` | Run browser in headless mode | `true` |
| `MAX_WORKERS` | Parallel processing workers | `20` |

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
│  TranslationService │ FileService │ ScrapingService       │
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
