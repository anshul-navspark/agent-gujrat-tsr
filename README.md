# Gujarat TSR Agent

A comprehensive automation solution for fetching land records from the Gujarat AnyRoR portal and generating Title Search Reports (TSR) using AI-powered document processing.

## 🚀 Features

- **Land Record Scraping**: Automated fetching of land records from the Gujarat AnyRoR website
- **AI-Powered CAPTCHA Solving**: Uses Google Gemini AI to solve CAPTCHAs
- **TSR Generation**: Generates professional Title Search Reports from land record PDFs
- **Batch Processing**: Process multiple records from Excel files with parallel execution
- **Multi-Language Support**: English to Gujarati translation for form inputs
- **Cloud Deployment**: Deployable on Google Cloud Run for serverless operation
- **Streamlit UI**: User-friendly web interface for record processing

## 📁 Project Structure

```
gujrat_tsr_agent/
├── core/                      # Core domain models and interfaces
│   ├── models.py              # Domain models (LandRecordRequest, APIResponse)
│   ├── interfaces.py          # Service interfaces (ITranslationService, etc.)
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
│   │   ├── single_record_form.py
│   │   ├── batch_processing_form.py
│   │   └── results_display.py
│   └── services/              # Streamlit-specific services
│       └── streamlit_service.py
│
├── anyror/                    # AnyRoR scraping module
│   ├── captcha_solver.py      # AI CAPTCHA solving
│   ├── webdriver_manager.py   # Selenium WebDriver management
│   └── scraper.py             # Main scraping logic
│
├── tsr_generator/             # TSR document generation
│   ├── extractors/            # PDF data extraction
│   ├── document/              # DOCX generation
│   └── processors/            # Data processing
│
├── utils/                     # Utility modules
│   ├── json_translations.py   # Translation dictionary management
│   ├── survey_utils.py        # Survey number utilities
│   ├── ai_column_detector.py  # AI column mapping
│   └── logging_config.py      # Centralized logging
│
├── tests/                     # Test suite
│   ├── conftest.py            # Pytest fixtures
│   ├── test_services.py       # Service layer tests
│   ├── test_api.py            # API endpoint tests
│   └── utils/                 # Test utilities
│
├── api/
│   ├── __init__.py
│   ├── server.py              # FastAPI backend server
│   ├── dependencies.py        # Dependency injection
│   └── middleware.py          # Custom middleware
├── Dockerfile                 # Container configuration
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## 🛠️ Installation

### Prerequisites

- Python 3.11+
- Google Chrome (for web scraping)
- ChromeDriver (automatically managed)
- Google Gemini API key

### Local Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd gujrat_tsr_agent
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY
   ```

5. **Run the API server**
   ```bash
   uvicorn api.server:app --host 0.0.0.0 --port 8000
   ```

6. **Run the Streamlit app** (in a separate terminal)
   ```bash
   streamlit run app/streamlit_app_cloud.py
   ```

## 🚀 Usage

### Single Record Processing

1. Open the Streamlit app in your browser
2. Navigate to the "Single Record" tab
3. Enter District, Taluka, Village, and Survey Number
4. Click "Generate TSR"
5. Download the generated DOCX and PDF files

### Batch Processing

1. Prepare an Excel file with columns: District, Taluka, Village, Survey Number
2. Go to the "Batch (Excel)" tab
3. Upload your Excel file
4. Map the columns to the required fields
5. Click "Start Batch Processing"
6. Download results from the "Results" tab

### API Usage

```bash
# Health check
curl http://localhost:8000/health

# Process a single record
curl -X POST http://localhost:8000/process-record \
  -H "Content-Type: application/json" \
  -d '{"district": "Kutch", "taluka": "Bhuj", "village": "Trambo", "survey_number": "32"}'
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run only unit tests
pytest -m "not integration"

# Run integration tests
pytest -m integration
```

## 🐳 Docker Deployment

```bash
# Build the Docker image
docker build -t gujarat-tsr-agent .

# Run the container
docker run -p 8000:8000 -e GEMINI_API_KEY=your_key gujarat-tsr-agent
```

## ☁️ Cloud Run Deployment

```bash
# Build and push to Container Registry
gcloud builds submit --tag gcr.io/YOUR_PROJECT/gujarat-tsr-agent

# Deploy to Cloud Run
gcloud run deploy gujarat-tsr-agent \
  --image gcr.io/YOUR_PROJECT/gujarat-tsr-agent \
  --platform managed \
  --region asia-south1 \
  --memory 4Gi \
  --timeout 1200 \
  --set-env-vars GEMINI_API_KEY=your_key
```

## 📝 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key for AI features | Required |
| `HEADLESS` | Run browser in headless mode | `true` |
| `CAPTCHA_TIMEOUT` | CAPTCHA solving timeout (seconds) | `30` |
| `CAPTCHA_MAX_RETRIES` | Max CAPTCHA retry attempts | `3` |
| `MAX_WORKERS` | Parallel processing workers | `20` |

### Streamlit Secrets

For Streamlit Cloud deployment, add secrets to `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "your_key"
API_URL = "https://your-cloud-run-url.run.app"
API_TIMEOUT = 1200
MAX_WORKERS = 20
```

## 🏗️ Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

## 📄 License

This project is licensed under the MIT License.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📞 Support

For questions or issues, please open a GitHub issue or contact the maintainers.
