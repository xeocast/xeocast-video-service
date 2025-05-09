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
    R2_ENDPOINT_URL: str = "https://<ACCOUNT_ID>.r2.cloudflarestorage.com" # Replace <ACCOUNT_ID>
    R2_ACCESS_KEY_ID: str
    R2_SECRET_ACCESS_KEY: str
    R2_BUCKET_NAME: str = "video-service-files"

    # YouTube OAuth Settings
    YOUTUBE_SCOPES: list[str] = ["https://www.googleapis.com/auth/youtube.upload"]
    YOUTUBE_OAUTH_CALLBACK_PATH: str = "/oauth2callback" # The path for OAuth callback
    YOUTUBE_REDIRECT_URI: str = "" # Will be set by validator based on APP_ENV and BASE_URL

    # Temporary Directory for Storing Auth Tokens
    TMP_AUTH_DIR: Path = Path("tmp-auth")

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
        else: # Default to development
            current_base_url = dev_base_url
        
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