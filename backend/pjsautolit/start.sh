#!/bin/bash

# Set Redis URL for Celery broker (update this with your actual Redis URL)
export CELERY_BROKER_URL="rediss://red-crts7tggph6c73daq840:dEPiQFWEmuEz7s6cZdcCA1Te0kuwnTdK@oregon-redis.render.com:6379"

# Start Celery worker in the background
celery -A pjsautolit worker --pool=solo -l info &
CELERY_PID=$!

# Function to forward signals to child processes
forward_signal() {
    kill -$1 $CELERY_PID
}

# Set up signal handling
trap 'forward_signal TERM' TERM
trap 'forward_signal INT'  INT

# Start Gunicorn in the foreground
exec gunicorn --bind 0.0.0.0:8000 --timeout 0 pjsautolit.wsgi:application