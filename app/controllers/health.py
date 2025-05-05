from fastapi import APIRouter

from app.models.api_models import HealthResponse

router = APIRouter()

@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Checks the operational status of the API service."""
    return HealthResponse(status="healthy") 