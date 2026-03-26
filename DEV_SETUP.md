# Dev Setup — Gujarat TSR Agent

## Prerequisites
- Python 3.11
- Google Chrome installed
- Gemini API key

## Setup

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `.env` in project root:
```
GEMINI_API_KEY=your_key_here
```

Create `.streamlit/secrets.toml`:
```toml
API_URL = "http://localhost:8000"
API_TIMEOUT = 1200
API_MAX_RETRIES = 0
```

## Run

**Terminal 1 — FastAPI backend:**
```bash
source venv/bin/activate
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Streamlit UI:**
```bash
source venv/bin/activate
streamlit run app/streamlit_app_cloud.py --server.port 8501
```

Open **http://localhost:8501**

## Usage
Single Record tab → enter District / Taluka / Village / Survey No → Generate → download ZIP (DOCX + PDF).

**Example:** Porbandar / Porbandar / Miyani / 1352

## Notes
- First run ~2 min (scrapes AnyRoR + AI generation). Repeat runs ~5s (local cache).
- Cache lives at `~/.cache/gujrat_tsr_agent/cache/` — delete to force fresh fetch.
- If you use Claude CLI, just ask it to restart the servers or debug errors directly.
