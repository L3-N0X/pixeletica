# Python 3.12-based image for Pixeletica API
FROM python:3.12-slim

# Set entrypoint script
COPY src/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Expose API port
EXPOSE 8000

# Create necessary directories with appropriate permissions
RUN mkdir -p /app/out/api_tasks \
    && mkdir -p /app/out/rendered \
    && mkdir -p /app/out/exports \
    && mkdir -p /app/out/logs \
    && mkdir -p /app/out/cache

# Create and set up a non-root user
RUN useradd -m pixeletica \
    && chown -R pixeletica:pixeletica /app
USER pixeletica

# Command to run the API
CMD ["python", "-m", "pixeletica.api.main"]
