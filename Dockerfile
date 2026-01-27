# PSV Calculator Backend - Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .

# Copy frontend files for static serving
COPY frontend/ ./static/

# Expose port (Railway sets PORT dynamically)
EXPOSE ${PORT:-8000}

# Run the application (Railway overrides via startCommand in railway.json)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
