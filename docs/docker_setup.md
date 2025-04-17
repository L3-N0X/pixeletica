# Docker Setup and Deployment Guide for Pixeletica

This document provides detailed information about the Docker setup for Pixeletica and how to deploy it using GitHub Actions.

## Project Architecture

Pixeletica consists of three main services:

1. **API Service**: A FastAPI application that handles HTTP requests for image conversion
2. **Worker Service**: A Celery worker that processes background tasks
3. **Redis**: Message broker for task queueing and result storage

## Docker Compose Configuration

The `docker-compose.yml` file defines the services and their configurations:

### API Service

```yaml
api:
  build:
    context: .
    dockerfile: Dockerfile
  image: ${DOCKER_REGISTRY:-ghcr.io}/${DOCKER_NAMESPACE:-your-username}/pixeletica-api:${TAG:-latest}
  # ... other configuration
```

### Worker Service

```yaml
worker:
  build:
    context: .
    dockerfile: src/docker/worker.dockerfile
  image: ${DOCKER_REGISTRY:-ghcr.io}/${DOCKER_NAMESPACE:-your-username}/pixeletica-worker:${TAG:-latest}
  # ... other configuration
```

### Redis Service

```yaml
redis:
  image: redis:7-alpine
  command: redis-server --appendonly yes --maxmemory ${REDIS_MEMORY_LIMIT:-256mb} --maxmemory-policy ${REDIS_MEMORY_POLICY:-volatile-lru}
  # ... other configuration
```

## Environment Variables

The Docker Compose file supports many environment variables to customize the deployment:

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCKER_REGISTRY` | `ghcr.io` | Container registry to use |
| `DOCKER_NAMESPACE` | `your-username` | Username or organization in the registry |
| `TAG` | `latest` | Container tag to use |
| `PIXELETICA_API_PORT` | `8000` | Port to expose the API on the host |
| `LOG_LEVEL` | `info` | Logging level for all services |
| `MAX_UPLOAD_SIZE` | `10485760` (10MB) | Maximum upload size for the API |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `API_CPU_LIMIT` | `1` | CPU limit for API container |
| `API_MEMORY_LIMIT` | `1G` | Memory limit for API container |
| `WORKER_CPU_LIMIT` | `2` | CPU limit for worker container |
| `WORKER_MEMORY_LIMIT` | `2G` | Memory limit for worker container |
| `WORKER_REPLICAS` | `1` | Number of worker replicas |
| `REDIS_MEMORY_LIMIT` | `256mb` | Memory limit for Redis |
| `REDIS_MEMORY_POLICY` | `volatile-lru` | Redis memory policy |

## Deployment with GitHub Actions

Three GitHub Actions workflows are provided:

1. **build-api.yml**: Builds and publishes just the API container
2. **build-worker.yml**: Builds and publishes just the worker container
3. **build-all.yml**: Builds and publishes both containers

### Workflow Trigger Events

- **Push to main/master**: Automatically builds and publishes containers
- **Release publication**: Tags containers with the release version
- **Manual dispatch**: Allows manual builds with custom tags

### Setting Up GitHub Actions

1. Ensure your repository has access to publish packages
2. Set up the necessary secrets:
   - `GITHUB_TOKEN` (automatically provided)

### Container Registry

By default, containers are published to GitHub Container Registry (ghcr.io). To use a different registry, modify the `DOCKER_REGISTRY` environment variable in the workflow files or during deployment.

## Local Development

For local development:

```bash
# Start all services
docker-compose up

# Start specific services
docker-compose up api redis

# Start in detached mode
docker-compose up -d

# Scale workers
docker-compose up -d --scale worker=3
```

## Production Deployment

For production deployment:

```bash
# Create a .env file with your configuration
# Example:
# DOCKER_NAMESPACE=myorganization
# TAG=v1.0.0
# WORKER_REPLICAS=3

# Pull the latest images
docker-compose pull

# Deploy the stack
docker-compose up -d
```

## Scaling Workers

To scale worker processes:

1. Set the `WORKER_REPLICAS` environment variable in your deployment
2. Or use the `docker-compose up -d --scale worker=3` command

## Data Persistence

Two Docker volumes are created for persistent data:

1. **pixeletica_tasks_data**: Stores task data (input images, metadata, output files) in `/app/tasks`, shared between API and worker containers.
2. **redis_data**: Stores Redis data for queue persistence if the volume mount is uncommented in `docker-compose.yml`.

## Troubleshooting

- **API not starting**: Check Redis connectivity with `docker-compose logs api`
- **Worker not processing tasks**: Verify Celery status with `docker-compose exec worker celery -A pixeletica.api.services.task_queue.celery_app status`
- **Redis running out of memory**: Increase `REDIS_MEMORY_LIMIT` or adjust `REDIS_MEMORY_POLICY`
