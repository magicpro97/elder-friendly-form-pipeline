#!/bin/sh
# Start script for Railway deployment
# Ensures PORT variable is properly read and passed to uvicorn

PORT=${PORT:-8000}
echo "Starting uvicorn on port $PORT"
exec uvicorn app:app --host 0.0.0.0 --port $PORT
