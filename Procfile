web: python -c "from database import init_db; init_db()" && gunicorn app:app
worker: python scheduler.py