#!/bin/bash

# Start Gunicorn in the background
gunicorn --bind 0.0.0.0:8000 --timeout 0 pjsautolit.wsgi:application &

# Wait for the Django app to be ready
sleep 10

# Start Celery worker
celery -A pjsautolit worker --pool=solo -l info