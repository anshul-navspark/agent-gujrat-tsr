FROM python:3.9-slim

# Install system dependencies including Chromium and Chromedriver
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    build-essential \
    libpoppler-cpp-dev \
    pkg-config \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Run the application
# Run the application
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8080"]
