from fastapi import APIRouter, Request, HTTPException, status, Body
import logging

from app.models.api_models import TestCallbackResponse, ErrorResponse, TestCallbackPayload

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "/test-callback",
    response_model=TestCallbackResponse,
    tags=["Testing"],
    summary="Test Callback Endpoint",
    description="Accepts any JSON POST payload and logs it. Useful for testing callback handling.",
    responses={500: {"model": ErrorResponse}}
)
async def test_callback(payload: TestCallbackPayload = Body(...)):
    """Logs the received JSON payload from a POST request."""
    try:
        logger.info(f"Received test callback with payload: {payload.data}")
        return TestCallbackResponse(received=True)
    except Exception as e:
        logger.error(f"Error processing test callback: {e}", exc_info=True)
        # Return a 500 error compliant with the ErrorResponse model if possible
        # Note: HTTPException bypasses normal response model handling for errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"received": False, "error": f"Failed to process request body: {e}"} # Custom detail structure
        )
        # Alternatively, structure the detail according to ErrorResponse if preferred:
        # raise HTTPException(
        #     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        #     detail=ErrorResponse(error="Internal Server Error", message=f"Failed to process request body: {e}").model_dump()
        # ) 