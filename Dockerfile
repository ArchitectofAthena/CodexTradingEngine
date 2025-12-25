FROM python:3.11-slim

# Metadata
LABEL maintainer="EVE_Q Development Team"
LABEL description="EVE_Q SlurperBot v2 - Grace Economy Edition"
LABEL version="2.0.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create app user (don't run as root)
RUN useradd -m -u 1000 -s /bin/bash eveq

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=eveq:eveq . .

# Create necessary directories
RUN mkdir -p logs data/metrics data/ipfs_logs && \
    chown -R eveq:eveq logs data

# Switch to app user
USER eveq

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default command (simulation mode)
CMD ["python", "src/main.py"]
