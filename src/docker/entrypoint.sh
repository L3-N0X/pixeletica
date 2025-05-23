#!/bin/bash
set -e

# Function to verify Redis connection
function check_redis() {
    python -c "
import sys
import time
import redis
import os

redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
max_retries = 30
retry_interval = 2

for i in range(max_retries):
    try:
        r = redis.from_url(redis_url)
        r.ping()
        sys.exit(0)
    except redis.exceptions.ConnectionError:
        print(f'Redis not available yet, retrying in {retry_interval}s... ({i+1}/{max_retries})')
        time.sleep(retry_interval)

print('Failed to connect to Redis after several retries. Exiting.')
sys.exit(1)
"
}

# Make tasks directory if it doesn't exist
if [ ! -d /app/tasks ]; then
    mkdir -p /app/tasks
    echo "Created tasks directory"
fi

# Ensure output directory structure exists with correct permissions
if [ ! -d /app/out/api_tasks ]; then
    mkdir -p /app/out/api_tasks
    echo "Created output directory structure: api_tasks"
fi

if [ ! -d /app/out/rendered ]; then
    mkdir -p /app/out/rendered
    echo "Created output directory structure: rendered"
fi

if [ ! -d /app/out/exports ]; then
    mkdir -p /app/out/exports
    echo "Created output directory structure: exports"
fi

if [ ! -d /app/out/logs ]; then
    mkdir -p /app/out/logs
    echo "Created output directory structure: logs"
fi

if [ ! -d /app/out/cache ]; then
    mkdir -p /app/out/cache
    echo "Created output directory structure: cache"
fi

# Check Redis connection if needed
if [ "$WAIT_FOR_REDIS" = "true" ]; then
    echo "Waiting for Redis to be ready..."
    check_redis
    echo "Redis is ready!"
fi

# If running celery worker, print info and execute the command
if [[ "$1" == "celery" && "$2" == "-A"* && "$3" == *worker* ]]; then
    echo "Starting Celery worker: $@"
    exec "$@" # Removed gosu pixeletica
fi

# Default: execute the command passed to the entrypoint
echo "Executing command: $@"
exec "$@" # Removed gosu pixeletica
