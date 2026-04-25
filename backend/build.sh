#!/usr/bin/env bash
# exit on error
set -o errexit

# Change to the directory where the script is located
cd "$(dirname "$0")"

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Running migrations..."
python manage.py migrate

echo "Seeding database..."
python manage.py seed
