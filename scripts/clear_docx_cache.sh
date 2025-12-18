#!/bin/bash

# Script to manually clear all TSR DOCX files from the GCS cache.
# This forces regeneration of TSR documents while preserving scraped PDFs.

BUCKET_NAME="neon-alcove-479309-q3-tsr-cache"

echo "Clearing TSR DOCX files from gs://${BUCKET_NAME}/cache/..."

gcloud storage rm "gs://${BUCKET_NAME}/cache/*/tsr.docx"

if [ $? -eq 0 ]; then
    echo "Successfully cleared DOCX cache."
else
    echo "Failed to clear DOCX cache or no files found."
fi
