# Use Python 3.12 slim base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app/backend

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies if needed (none obvious required)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY backend/requirements.txt /app/backend/requirements.txt

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy only required backend application files
COPY backend/app /app/backend/app

# Create data directories (will be mounted as volume)
RUN mkdir -p /app/data/uploads /app/data/monitoring

# Bind to the platform-assigned port. Render injects PORT at runtime; the
# fallback keeps local Docker Compose working (it maps "8000:8000").
ENV PORT=8000
EXPOSE $PORT

# Run the application (download workbook from WORKBOOK_URL if missing)
CMD ["sh", "-c", "if [ -n \"$WORKBOOK_URL\" ] && [ ! -f \"$WORKBOOK_PATH\" ]; then mkdir -p $(dirname \"$WORKBOOK_PATH\"); curl -L -o \"$WORKBOOK_PATH\" \"$WORKBOOK_URL\" || true; fi; exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]