from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from app.models.settings import settings

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    """Dependency that verifies the X-API-Key header."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authenticated: API key required in X-API-Key header.",
        )
    if api_key == settings.API_KEY:
        return api_key
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials: Invalid API Key.",
        ) 