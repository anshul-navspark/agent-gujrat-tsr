FROM python:3.11-slim

# Install system dependencies including Chromium and Chromedriver
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    build-essential \
    libpoppler-cpp-dev \
    pkg-config \
    python3-dev \
    fonts-indic \
    fonts-noto \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV USE_OPTIMIZED_EXTRACTION=true
ENV GEMINI_MODEL_NAME=gemini-2.5-flash

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cache busting argument - forces rebuild from here when value changes
ARG CACHEBUST=1

# Copy application code
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Run the application
# Run the application
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8080"]
