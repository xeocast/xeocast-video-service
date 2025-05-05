from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    """Application settings."""
    API_KEY: str = "default_api_key" # Default for local development
    BASE_URL: str = "http://localhost:8000" # Base URL for constructing absolute URLs
    STATIC_DIR: str = "static"
    SIGNATURE_SECRET_KEY: str = "default_secret_key" # Secret for signing URLs
    SIGNATURE_EXPIRATION_SECONDS: int = 24 * 60 * 60 # 24 hours
    CLEANUP_INTERVAL_HOURS: int = 1 # How often to run cleanup
    MAX_VIDEO_AGE_HOURS: int = 48 # Max age for videos before deletion

    class Config:
        env_file = '.env' # Load environment variables from .env file if it exists
        extra = 'ignore' # Ignore extra fields from environment

settings = Settings()

# Ensure static directory exists
os.makedirs(settings.STATIC_DIR, exist_ok=True) 