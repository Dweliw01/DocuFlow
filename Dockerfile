# DocuFlow Backend Dockerfile
# Multi-stage build for smaller image size

# Stage 1: Build stage with all dependencies
FROM python:3.11-slim as builder

# Install system dependencies for PDF processing
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime stage with minimal footprint
FROM python:3.11-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create app directory
WORKDIR /app

# Copy application code
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY storage/ /app/storage/
COPY .env.example /app/.env.example

# Create necessary directories
RUN mkdir -p /app/storage/uploads \
    /app/storage/processed \
    /app/storage/logs \
    /app/storage/database

# Set permissions
RUN chmod -R 755 /app/storage

# Create non-root user for security
RUN useradd -m -u 1000 docuflow && chown -R docuflow:docuflow /app
USER docuflow

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
