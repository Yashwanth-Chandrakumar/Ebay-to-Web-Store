# Use an official Python runtime as the base image
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=pjsautolit.settings

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# Install system dependencies
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*


# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project code into the container
COPY . /app/

# Create a non-root user
RUN useradd -m myuser
RUN chown -R myuser:myuser /app
USER myuser

# Create a stage for the Django app
FROM base as django
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--timeout", "0", "pjsautolit.wsgi:application"]

# Create a stage for the Celery worker
FROM base as celery
CMD ["celery", "-A", "pjsautolit", "worker", "--pool=solo", "-l", "info"]

# Create a stage for the combined app (for Render)
FROM base as combined
COPY --chown=myuser:myuser start.sh /app/start.sh
RUN chmod +x /app/start.sh
CMD ["/app/start.sh"]
