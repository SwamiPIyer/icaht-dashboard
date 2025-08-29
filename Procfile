web: gunicorn wsgi:appweb: gunicorn wsgi:app
release: python -c "from app import create_app; app = create_app(); app.app_context().push(); from models import db; db.create_all()"web: gunicorn app:app
release: python -c "from app import app, db; app.app_context().push(); db.create_all()"
