FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for couchbase SDK + TLS certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake libssl-dev ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy everything
COPY . .

# Install django-couchbase-orm package + example dependencies
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir -r example/requirements.txt

# Collect static files
RUN cd example && python manage.py collectstatic --noinput 2>/dev/null || true

WORKDIR /app/example

EXPOSE ${PORT:-8000}

CMD uvicorn beerapp.asgi:application --host 0.0.0.0 --port ${PORT:-8000}
