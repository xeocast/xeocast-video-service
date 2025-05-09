import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import JSONResponse, HTMLResponse

from app.models.youtube_models import GetYoutubeAuthUrlRequest, GetYoutubeAuthUrlResponse
from app.services.youtube_oauth_service import youtube_oauth_service, YouTubeOAuthService
from app.models.api_models import ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post(
    "/get-youtube-auth-url",
    response_model=GetYoutubeAuthUrlResponse,
    summary="Get YouTube OAuth Authorization URL",
    tags=["YouTube Authentication"],
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "Client secret file not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_youtube_auth_url(
    request_data: GetYoutubeAuthUrlRequest,
    service: YouTubeOAuthService = Depends(lambda: youtube_oauth_service)
):
    """
    Initiates the YouTube OAuth2 flow by generating an authorization URL.

    - **youtube_channel_id**: The ID of the YouTube channel to authorize.
    - **client_secret_filename**: The filename (key in R2 bucket) of the OAuth client secret JSON.
    """
    try:
        auth_url = service.generate_auth_url(
            youtube_channel_id=request_data.youtube_channel_id,
            client_secret_filename=request_data.client_secret_filename
        )
        return GetYoutubeAuthUrlResponse(authorization_url=auth_url)
    except HTTPException as e:
        # Re-raise HTTPExceptions to let FastAPI handle them
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in /get-youtube-auth-url: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error="InternalServerError", message=str(e)).model_dump()
        )

@router.get(
    "/oauth2callback",
    summary="OAuth2 Callback Handler (Google Redirect)",
    tags=["YouTube Authentication"],
    response_class=HTMLResponse,
    responses={
        200: {"description": "Authentication successful. See HTML response."},
        400: {"description": "Invalid request, code, or state. See HTML response for details."},
        500: {"description": "Internal server error. See HTML response for details."}
    }
)
async def oauth2callback(
    code: str = Query(..., description="The authorization code from Google OAuth redirect."),
    state: str = Query(..., description="The state parameter from Google OAuth redirect."),
    service: YouTubeOAuthService = Depends(lambda: youtube_oauth_service)
):
    """
    Handles the OAuth2 callback from Google. Exchanges the authorization code for an access token.
    This endpoint is specified as the YOUTUBE_REDIRECT_URI in settings and Google Cloud Console.
    It returns an HTML page to the user's browser.
    """
    logger.info(f"Received OAuth2 callback via GET. Code: {code[:20]}... State: {state}")
    try:
        youtube_channel_id, client_secret_filename = service.exchange_code_for_token(auth_code=code, state=state)
        
        html_content = f"""
        <html>
            <head><title>Authentication Successful</title></head>
            <body>
                <h1>Authentication Successful!</h1>
                <p>YouTube OAuth configured successfully for channel '{youtube_channel_id}' using client secret config '{client_secret_filename}'.</p>
                <p>You can now close this window.</p>
            </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=status.HTTP_200_OK)
    except HTTPException as e:
        logger.error(f"OAuth2 callback error for state {state}. Status: {e.status_code}, Detail: {e.detail}", exc_info=True)
        html_error_content = f"""
        <html>
            <head><title>Authentication Failed</title></head>
            <body>
                <h1>Authentication Failed</h1>
                <p>An error occurred during the OAuth2 process.</p>
                <p><b>Error Code:</b> {e.status_code}</p>
                <p><b>Details:</b> {e.detail}</p>
                <p>Please try again or contact support if the issue persists.</p>
            </body>
        </html>
        """
        return HTMLResponse(content=html_error_content, status_code=e.status_code)
    except Exception as e:
        logger.error(f"Unexpected error in /oauth2callback: {e}", exc_info=True)
        html_error_content = f"""
        <html>
            <head><title>Authentication Failed</title></head>
            <body>
                <h1>Authentication Failed</h1>
                <p>An unexpected internal error occurred. Please try again later.</p>
                <!-- <p>Details: {str(e)}</p> --> <!-- Avoid exposing too much detail in production -->
            </body>
        </html>
        """
        return HTMLResponse(content=html_error_content, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) 