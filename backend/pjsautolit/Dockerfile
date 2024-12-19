# Use a Python base image with build dependencies (not slim)
FROM python:3.11

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=pjsautolit.settings

# Set the working directory in the container
WORKDIR /app

# Install Python dependencies (no need to install system dependencies like gcc, etc.)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir redis==5.0.1

# Copy the project code into the container
COPY . /app/

# Copy the start script and set permissions
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Create a non-root user and change ownership of the app directory
RUN useradd -m myuser
RUN chown -R myuser:myuser /app

# Switch to non-root user
USER myuser

# Expose the port Gunicorn will run on
EXPOSE 8000

# Run the start script
CMD ["/app/start.sh"]
