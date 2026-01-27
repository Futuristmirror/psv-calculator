# PSV Calculator - Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Copy frontend into backend directory so FastAPI can serve it
COPY frontend/ ./frontend/

# Railway assigns PORT dynamically via environment variable
ENV PORT=8000

# Health check uses the dynamic PORT
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run the application on the dynamic PORT
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
