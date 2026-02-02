# Dockerfile for Headlines Client
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY config/ config/
COPY generated/ generated/

# Create __init__.py for generated module
RUN touch generated/__init__.py

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV APP_PROFILE=tcp

# Run the client
CMD ["python", "-m", "src.client"]
