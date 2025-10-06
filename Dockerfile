# Use a small Python base
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Install system deps
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Copy files and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use an environment variable to control Flask config in the container
ENV FLASK_ENV=production
ENV PYTHONPATH=/app

# Expose port and run with gunicorn
EXPOSE 8000
CMD ["gunicorn", "--workers", "3", "--bind", "0.0.0.0:8000", "app:app"]