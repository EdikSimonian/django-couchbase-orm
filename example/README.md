# Wagtail + Couchbase Example

A Wagtail CMS site using Couchbase as the database via `django-couchbase-orm`.

## Setup

1. Start Couchbase:
```bash
docker run -d --name couchbase -p 8091-8097:8091-8097 -p 11210-11211:11210-11211 couchbase/server:latest
```

2. Create a bucket named `mybucket` via the Couchbase admin (http://localhost:8091).

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Copy env file:
```bash
cp .env.example .env
```

5. Run migrations:
```bash
python manage.py migrate
```

6. Create admin user:
```bash
python manage.py createsuperuser
```

7. Run the server:
```bash
python manage.py runserver
```

8. Visit:
   - Site: http://localhost:8000
   - Wagtail admin: http://localhost:8000/admin/
