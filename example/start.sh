#!/bin/bash
set -e

# Run migrations
python manage.py migrate --noinput

# Create superuser if env vars are set and no users exist
if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
    python manage.py createsuperuser --noinput 2>/dev/null || true
fi

# Start gunicorn
exec gunicorn mysite.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 2
