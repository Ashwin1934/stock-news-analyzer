FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY protos/ ./protos/
COPY config/ ./config/
COPY generated/ ./generated/
COPY src/ ./src/

# Default profile
ENV APP_PROFILE=tcp

# Expose ports
EXPOSE 50051

CMD ["python", "src/inference_server.py"]