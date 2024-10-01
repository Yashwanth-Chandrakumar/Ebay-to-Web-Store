#!/bin/bash

# Set Redis URL for Celery broker (update this with your actual Redis URL)
export CELERY_BROKER_URL="rediss://red-crts7tggph6c73daq840:dEPiQFWEmuEz7s6cZdcCA1Te0kuwnTdK@oregon-redis.render.com:6379"

# Start Gunicorn in the background
gunicorn --bind 0.0.0.0:8000 --timeout 0 pjsautolit.wsgi:application &

# Wait for the Django app to be ready
sleep 10

# Start Celery worker
celery -A pjsautolit worker --pool=solo -l info