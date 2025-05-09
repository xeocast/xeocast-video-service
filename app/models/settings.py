from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
import os
from pathlib import Path
from typing import Literal

class Settings(BaseSettings):
    """Application settings."""
    API_KEY: str = "default_api_key" # Default for local development
    # BASE_URL will be set dynamically
    STATIC_DIR: str = "static"
    SIGNATURE_SECRET_KEY: str = "default_secret_key" # Secret for signing URLs
    SIGNATURE_EXPIRATION_SECONDS: int = 24 * 60 * 60 # 24 hours
    CLEANUP_INTERVAL_HOURS: int = 1 # How often to run cleanup
    MAX_VIDEO_AGE_HOURS: int = 48 # Max age for videos before deletion

    # Environment Configuration
    APP_ENV: Literal["development", "production"] = "development"
    DEV_BASE_URL: str = "http://localhost:8000"
    PROD_BASE_URL: str = "https://video-service.xeocast.com" # Your production base URL
    BASE_URL: str = "" # Will be set by validator below

    # Cloudflare R2 Settings
    R2_ENDPOINT_URL: str # Example: "https://<ACCOUNT_ID>.r2.cloudflarestorage.com"
    
    # Read-Only Credentials (for client secrets, source files)
    R2_RO_ACCESS_KEY_ID: str
    R2_RO_SECRET_ACCESS_KEY: str

    # Read-Write Credentials (for output video files)
    R2_RW_ACCESS_KEY_ID: str
    R2_RW_SECRET_ACCESS_KEY: str

    # Bucket Names (Production)
    R2_CLIENT_SECRETS_BUCKET_PROD: str = "video-service-files"
    R2_VIDEO_SOURCE_BUCKET_PROD: str = "video-source-files"
    R2_VIDEO_OUTPUT_BUCKET_PROD: str = "video-output-files"

    # Bucket Names (Development)
    R2_CLIENT_SECRETS_BUCKET_DEV: str = "video-service-files" # Assuming same for secrets
    R2_VIDEO_SOURCE_BUCKET_DEV: str = "video-source-files-preview"
    R2_VIDEO_OUTPUT_BUCKET_DEV: str = "video-output-files-preview"

    # Resolved Bucket Names (set by validator)
    R2_CLIENT_SECRETS_BUCKET: str = ""
    R2_VIDEO_SOURCE_BUCKET: str = ""
    R2_VIDEO_OUTPUT_BUCKET: str = ""

    # YouTube OAuth Settings
    YOUTUBE_SCOPES: list[str] = [
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.force-ssl" # Added for broader permissions
    ]
    YOUTUBE_OAUTH_CALLBACK_PATH: str = "/oauth2callback" # The path for OAuth callback
    YOUTUBE_REDIRECT_URI: str = "" # Will be set by validator based on APP_ENV and BASE_URL

    # Temporary Directory for Storing Auth Tokens
    TMP_AUTH_DIR: Path = Path("tmp-auth")

    # Temporary directory for downloads and other operations
    TMP_DIR: Path = Path("tmp")

    # Callback settings
    CALLBACK_TIMEOUT_SECONDS: int = 30 # Default timeout for callback requests

    @model_validator(mode='after')
    def set_dynamic_urls(cls, values):
        # Pydantic v2 style for accessing field values from the model instance being validated
        # For 'values' in 'after' mode, it's the model instance itself.
        # However, to modify fields, it's common to work with a dict representation if needed,
        # but here we can assign directly if 'values' is the model instance.
        # Let's assume 'values' is the model instance for direct attribute access and modification.
        # If 'values' were a dict, we'd use values.get('APP_ENV'), etc.
        # For BaseSettings, it's often simpler to re-construct or assign.
        # The Pydantic docs show 'values' as the model instance for 'after' mode.
        
        app_env = values.APP_ENV # Direct attribute access
        dev_base_url = values.DEV_BASE_URL
        prod_base_url = values.PROD_BASE_URL
        oauth_callback_path = values.YOUTUBE_OAUTH_CALLBACK_PATH

        current_base_url = ""
        if app_env == "production":
            current_base_url = prod_base_url
            values.R2_CLIENT_SECRETS_BUCKET = values.R2_CLIENT_SECRETS_BUCKET_PROD
            values.R2_VIDEO_SOURCE_BUCKET = values.R2_VIDEO_SOURCE_BUCKET_PROD
            values.R2_VIDEO_OUTPUT_BUCKET = values.R2_VIDEO_OUTPUT_BUCKET_PROD
        else: # Default to development
            current_base_url = dev_base_url
            values.R2_CLIENT_SECRETS_BUCKET = values.R2_CLIENT_SECRETS_BUCKET_DEV
            values.R2_VIDEO_SOURCE_BUCKET = values.R2_VIDEO_SOURCE_BUCKET_DEV
            values.R2_VIDEO_OUTPUT_BUCKET = values.R2_VIDEO_OUTPUT_BUCKET_DEV
        
        values.BASE_URL = current_base_url
        values.YOUTUBE_REDIRECT_URI = f"{current_base_url}{oauth_callback_path}"
        
        return values

    # Pydantic v2 model_config
    model_config = SettingsConfigDict(
        env_file='.env',
        extra='ignore',
        env_file_encoding='utf-8'
    )

settings = Settings()

# Ensure static directory exists
static_dir_path = Path(settings.STATIC_DIR)
if not static_dir_path.exists():
    static_dir_path.mkdir(parents=True, exist_ok=True)

# Ensure tmp-auth directory exists
if not settings.TMP_AUTH_DIR.exists():
    settings.TMP_AUTH_DIR.mkdir(parents=True, exist_ok=True)

# Ensure tmp directory exists
if not settings.TMP_DIR.exists():
    settings.TMP_DIR.mkdir(parents=True, exist_ok=True) 