#!/bin/bash

if [ "$PROCESS_TYPE" = "web" ]; then
    echo "Starting Django application..."
    gunicorn --bind 0.0.0.0:$PORT --timeout 0 pjsautolit.wsgi:application
elif [ "$PROCESS_TYPE" = "worker" ]; then
    echo "Starting Celery worker..."
    celery -A pjsautolit worker --pool=solo -l info
else
    echo "Invalid PROCESS_TYPE. Must be 'web' or 'worker'."
    exit 1
fi