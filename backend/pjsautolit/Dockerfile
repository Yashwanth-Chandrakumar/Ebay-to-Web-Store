# Use an official Python runtime as the base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=pjsautolit.settings \
    # Add this to reduce pip cache
    PIP_NO_CACHE_DIR=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# Combined into a single RUN to reduce layers
RUN apt-get update && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update && \
    apt-get install -y \
        default-libmysqlclient-dev \
        gcc \
        libpq-dev \
        python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/cache/apt/archives/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir redis==5.0.1 \
    && rm -rf ~/.cache/pip/*

# Create a non-root user before copying files
RUN useradd -m myuser

# Copy the project code and start script into the container
COPY --chown=myuser:myuser . /app/
COPY --chown=myuser:myuser start.sh /app/start.sh

# Set permissions
RUN chmod +x /app/start.sh \
    && chown -R myuser:myuser /app

# Switch to non-root user
USER myuser

# Expose the port Gunicorn will run on
EXPOSE 8000

# Run the start script
CMD ["/app/start.sh"]
