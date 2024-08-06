# Use an official Python runtime as the base image
FROM python:3.11

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE=your_project_name.settings

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project code into the container
COPY . /app/

# Make migrations and migrate
RUN python manage.py makemigrations
RUN python manage.py migrate

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "pjsautolit.wsgi:application"]