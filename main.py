import logging
import os
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.controllers import health, tasks, video, test_callback
from app.models.settings import settings
from app.services.cleanup_service import cleanup_service
from app.services.signature_service import signature_service
from app.models.api_models import ErrorResponse

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- FastAPI App Initialization ---
# --- Lifespan Context Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup...")
    # Start background tasks
    cleanup_service.start()
    # Perform initial cleanup on startup
    await cleanup_service.cleanup_old_files()
    yield  # Application runs here
    # Shutdown logic
    logger.info("Application shutdown...")
    cleanup_service.stop()

app = FastAPI(
    title="XeoCast Video Service",
    description="API for generating and publishing videos asynchronously.",
    version="0.1.0",
    lifespan=lifespan
)

# --- Middleware for Signed URL Verification ---
@app.middleware("http")
async def verify_signed_url_middleware(request: Request, call_next):
    parsed_url = urlparse(str(request.url))
    path = parsed_url.path

    # Only apply signature verification to requests targeting the static path prefix
    static_path_prefix = "/static/"
    if path.startswith(static_path_prefix) and path != static_path_prefix: # Exclude the root listing
        # Extract query parameters
        query_params = parse_qs(parsed_url.query)

        # Verify signature
        if not signature_service.verify_signature(path, query_params):
            logger.warning(f"Invalid or expired signature for path: {path}")
            error_response = ErrorResponse(error="Forbidden", message="Invalid or expired signature.")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=error_response.model_dump()
            )
        logger.debug(f"Valid signature verified for path: {path}")

    response = await call_next(request)
    return response

# --- Static Files Mounting ---
# Note: The middleware handles auth; direct access via StaticFiles bypasses middleware.
# We will handle static file serving manually within an endpoint IF verification is needed before serving.
# However, for simplicity and standard practice, let's mount it but rely on the middleware.
# If middleware approach is insufficient, a dedicated endpoint for /static/{filename} would be needed.

static_dir_path = Path(settings.STATIC_DIR)
if not static_dir_path.exists():
    logger.info(f"Creating static directory: {static_dir_path}")
    static_dir_path.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")


# --- API Routers Inclusion ---
app.include_router(health.router)
app.include_router(tasks.router)
app.include_router(video.router)
app.include_router(test_callback.router)

# --- Root Endpoint (Optional) ---
@app.get("/", tags=["Root"], include_in_schema=False)
async def read_root():
    return {"message": "Welcome to XeoCast Video Service"}

# --- Run with Uvicorn (for local development) ---
# This block allows running directly with `python main.py`
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server...")
    # Get host and port from environment variables or use defaults
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=True # Enable auto-reload for development
    ) 