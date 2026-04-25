#!/usr/bin/env bash

# exit on error
set -o errexit

echo "Starting Playto Payout Engine..."

# Start Celery worker in background
echo "Starting Celery worker..."
celery -A config worker --loglevel=info &

# Start Celery beat in background
echo "Starting Celery beat..."
celery -A config beat --loglevel=info &

# Start Gunicorn in foreground
echo "Starting Gunicorn..."
gunicorn config.wsgi --bind 0.0.0.0:$PORT
