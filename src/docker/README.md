# Pixeletica Docker Setup

This directory contains Docker configuration for running the Pixeletica API in containerized environments.

## Architecture

The Docker setup consists of three main services:

1. **API**: The FastAPI web service that handles HTTP requests
2. **Worker**: Celery worker that processes background tasks like image conversion
3. **Redis**: Message broker for task queue and result storage

Data is shared between containers via Docker volumes.

## Configuration Options

All configuration can be done through environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PIXELETICA_API_HOST` | `0.0.0.0` | Host to bind the API server |
| `PIXELETICA_API_PORT` | `8000` | Port to bind the API server |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |

For more configuration options, see `docker-compose.override.yml.example`.

## Health Checks

All services include health checks to ensure they're running properly:

- **API**: Checks if the root endpoint returns a 200 status
- **Worker**: Tests the Celery worker with a ping command
- **Redis**: Verifies Redis is responding to ping commands

## Volumes

Two persistent volumes are created:

- `pixeletica_data`: Stores task-related files (shared between API and worker)
- `redis_data`: Stores Redis data for task queue persistence

## Advanced Usage

### Scaling Workers

To run multiple worker instances:

```bash
docker-compose up -d --scale worker=3
```

### Custom Redis Configuration

Create a `redis.conf` file in a `config` directory and update docker-compose.override.yml:

```yaml
redis:
  volumes:
    - ./config/redis.conf:/usr/local/etc/redis/redis.conf
  command: redis-server /usr/local/etc/redis/redis.conf
```

### Development Mode

For development, you can mount the source code directory:

```yaml
api:
  volumes:
    - ./pixeletica:/app/pixeletica
```

This allows changes to be reflected without rebuilding the container.
