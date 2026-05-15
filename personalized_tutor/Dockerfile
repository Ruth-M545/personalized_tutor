FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "tutor.asgi:application"]
