import logging

from fastapi import APIRouter, Query, Depends, HTTPException, status, BackgroundTasks

from app.models.youtube_models import YouTubeVideoDetailsResponse, YouTubeVideoNotFoundResponse
from app.models.api_models import ErrorResponse, YouTubeVideoUploadRequest, CreateTaskResponse, TaskType
from app.services.youtube_service import youtube_service, YouTubeService # Assuming singleton
from app.services.task_service import task_service # Added task_service
from app.services.youtube_video_service import youtube_video_service # Added youtube_video_service
from app.utils.dependencies import get_api_key # API Key protection

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/youtube/videos",
    tags=["YouTube Videos"],
    dependencies=[Depends(get_api_key)] # Protect all routes in this router
)

@router.get(
    "/{video_id}",
    response_model=YouTubeVideoDetailsResponse,
    summary="Get YouTube Video Status and Metadata",
    description="Fetches details like privacy status and published date for a given YouTube video ID.",
    responses={
        200: {"description": "Successfully retrieved video details."},
        401: {"model": ErrorResponse, "description": "Authentication failed (OAuth token issue or API key issue)."},
        404: {"model": YouTubeVideoNotFoundResponse, "description": "Video not found."},
        500: {"model": ErrorResponse, "description": "Internal server error or YouTube API error."}
    }
)
async def get_youtube_video_details(
    video_id: str,
    youtube_channel_id: str = Query(..., description="The YouTube Channel ID associated with the OAuth credentials.", example="UC_ExampleChannelID12345"),
    service: YouTubeService = Depends(lambda: youtube_service) # Dependency injection for the service
):
    """
    Retrieves metadata for a specific YouTube video, including its status (privacy)
    and snippet information (published date, title, description).

    Requires prior OAuth authentication for the given `youtube_channel_id` to access video data.
    The endpoint itself is also protected by an API key.
    """
    try:
        logger.info(f"Received request for YouTube video details: video_id={video_id}, channel_id={youtube_channel_id}")
        video_details = await service.get_video_details(video_id=video_id, youtube_channel_id=youtube_channel_id)

        if not video_details:
            logger.warning(f"Video not found: {video_id} for channel {youtube_channel_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=YouTubeVideoNotFoundResponse(video_id=video_id).model_dump()
            )
        
        logger.info(f"Successfully retrieved video details for video_id={video_id}")
        return video_details
    except HTTPException as http_exc: # Re-raise HTTPExceptions from the service or validation
        logger.error(f"HTTPException while getting video details for {video_id} on channel {youtube_channel_id}: {http_exc.detail}", exc_info=True)
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error getting video details for {video_id} on channel {youtube_channel_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(error="InternalServerError", message=str(e)).model_dump()
        )

# New endpoint for uploading videos
@router.post(
    "/upload",
    response_model=CreateTaskResponse,
    summary="Upload Video to YouTube",
    tags=["YouTube Videos"],
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid request parameters"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def upload_youtube_video(
    request_data: YouTubeVideoUploadRequest,
    background_tasks: BackgroundTasks,
):
    """
    Accepts video details and metadata to upload a video to YouTube asynchronously.

    The process involves:
    1. Creating a task for the upload.
    2. Downloading the video and thumbnail from R2 (handled by worker).
    3. Authenticating with YouTube using the channel ID's token (handled by worker).
    4. Uploading the video to YouTube (handled by worker).
    5. Optionally adding to a playlist and posting a first comment (handled by worker).
    6. Sending a callback with the final status (handled by worker).
    """
    try:
        new_task = task_service.create_task(
            task_type=TaskType.UPLOAD_YOUTUBE_VIDEO,
            details=request_data
        )
        logger.info(f"YouTube upload task created: {new_task.id} for channel {request_data.youtube_channel_id}")
        background_tasks.add_task(youtube_video_service.process_upload_task, new_task.id)
        
        return CreateTaskResponse(
            task_id=new_task.id,
            status=new_task.status,
            message="YouTube video upload task accepted and is being processed."
        )

    except Exception as e:
        logger.error(f"Error creating YouTube upload task: {e}", exc_info=True)
        error_response = ErrorResponse(error="TaskCreationError", message=f"Failed to create YouTube upload task: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response.model_dump()
        ) 