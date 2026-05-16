#!/bin/bash
# Quick startup script for the personalized tutor

set -e

VENV_BIN="./.venv/bin"
PYTHON="$VENV_BIN/python"

echo "🎓 Starting Personalized Learning Tutor"
echo "======================================"

# Activate venv
if [ ! -f "$VENV_BIN/python" ]; then
    echo "❌ Virtual environment not found. Please run: python -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

# Run migrations
echo "📦 Running migrations..."
$PYTHON manage.py migrate --noinput

# Collect static files
echo "📁 Collecting static files..."
$PYTHON manage.py collectstatic --noinput

# Start the dev server
echo "🚀 Starting development server on http://localhost:8000"
echo "Admin: http://localhost:8000/admin (user: admin)"
echo "Dashboard: http://localhost:8000/"
echo ""
echo "Note: WebSocket chat requires Redis + Daphne. Run with Docker for full features:"
echo "  docker-compose up --build"
echo ""

$PYTHON manage.py runserver 0.0.0.0:8000
