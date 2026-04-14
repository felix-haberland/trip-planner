#!/bin/bash

# Load environment variables from .env
if [ -f "$(dirname "$0")/.env" ]; then
    set -a
    source "$(dirname "$0")/.env"
    set +a
fi

cd "$(dirname "$0")/backend"
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
