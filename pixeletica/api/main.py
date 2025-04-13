"""
FastAPI application entry point for the Pixeletica API.

This module sets up the FastAPI application, includes routes,
and handles CORS, documentation, and middleware.
"""

import os
import logging
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
from typing import Dict, Any, List
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.middleware import RateLimitMiddleware
import redis.asyncio as redis

from pixeletica.api.routes import conversion, maps

# Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
RATE_LIMIT = "100/minute"  # 100 requests per minute

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("pixeletica.api")

# Create FastAPI app
app = FastAPI(
    title="Pixeletica API",
    description="API for converting images to Minecraft block art",
    version="0.1.0",
    docs_url=None,  # Disable default docs
    redoc_url=None,  # Disable default redoc
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Add rate limit middleware
app.add_middleware(RateLimitMiddleware, limit_value=RATE_LIMIT)

# Add routes
app.include_router(conversion.router)
app.include_router(maps.router)


@app.on_event("startup")
async def startup():
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        redis_instance = redis.from_url(redis_url)
        await FastAPILimiter.init(redis_instance)
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")


@app.get("/", tags=["health"])
async def root() -> Dict[str, Any]:
    """
    Root endpoint for health checks.

    Returns:
        Dictionary with API name, version, and status.
    """
    return {"name": "Pixeletica API", "version": "0.1.0", "status": "online"}


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """
    Custom Swagger UI endpoint.
    """
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - API Documentation",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler to catch unhandled errors.
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred"},
    )


# Add request validation middleware
@app.middleware("http")
async def validate_request(request: Request, call_next):
    """
    Middleware to validate incoming requests.
    """
    try:
        # Add your validation logic here
        # For example, check headers, query parameters, or request body
        if request.method == "POST":
            body = await request.json()
            # Example: Check if the image URL is present
            if "image_url" not in body:
                raise HTTPException(status_code=400, detail="Image URL is required")
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"detail": e.detail},
        )
    response = await call_next(request)
    return response


def start_api():
    """
    Start the API using uvicorn.

    This function is the entry point when running the API.
    """
    import uvicorn

    host = os.environ.get("PIXELETICA_API_HOST", "0.0.0.0")
    port = int(os.environ.get("PIXELETICA_API_PORT", 8000))

    logger.info(f"Starting Pixeletica API on {host}:{port}")
    uvicorn.run(
        "pixeletica.api.main:app", host=host, port=port, reload=True, log_level="info"
    )


if __name__ == "__main__":
    start_api()
