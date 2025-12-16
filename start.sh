#!/bin/bash
# Startup script for Cloud Run with warmup
# This script starts the server and optionally pre-warms heavy dependencies

set -e

# Optional: Pre-warm Python bytecode cache
if [ "$PREWARM_IMPORTS" = "true" ]; then
    echo "Pre-warming Python imports..."
    python -c "
import sys
sys.dont_write_bytecode = True

# Pre-import heavy modules to warm bytecode cache
try:
    import langchain_google_genai
    import langchain_core
    import selenium
    import pypdf
    print('Pre-warming complete')
except Exception as e:
    print(f'Pre-warming skipped: {e}')
"
fi


# Run cache clearing (conditionally clears DOCX if new version deployed)
echo "Checking for cache clearing..."
python scripts/clear_cache.py || echo "Cache clearing failed, but continuing startup..."

# Start uvicorn with optimizations
exec python -O -m uvicorn api.server:app \
    --host 0.0.0.0 \
    --port ${PORT:-8080} \
    --workers 1 \
    --loop uvloop \
    --http httptools \
    --no-access-log
