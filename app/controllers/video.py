from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status, Query, Body
from pydantic import HttpUrl
from typing import Optional

from app.models.api_models import (
    GenerateVideoResponse, UploadYoutubeVideoResponse,
    ErrorResponse, TaskType,
    GenerateVideoDetails, UploadYoutubeVideoDetails, BaseTaskDetails
)
from app.services.task_service import task_service
from app.utils.dependencies import get_api_key
from app.utils.background_tasks import run_generate_video_task, run_upload_youtube_video_task

router = APIRouter(
    tags=["Video"],
    dependencies=[Depends(get_api_key)],
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)

@router.get(
    "/generate-video",
    response_model=GenerateVideoResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate Video",
    description="Initiates an asynchronous task to generate a video from a background image and an audio file."
)
async def generate_video(
    background_tasks: BackgroundTasks,
    background_image_key: str = Query(..., description="R2 object key for the background image."),
    audio_file_key: str = Query(..., description="R2 object key for the audio file."),
    callback_url: HttpUrl = Query(..., description="URL to send the callback to after processing.")
):
    """Endpoint to start video generation using R2 object keys for source image and audio via query parameters."""
    try:
        payload = GenerateVideoDetails(
            background_image_key=background_image_key,
            audio_file_key=audio_file_key,
            callback_url=callback_url
        )
        task = task_service.create_task(TaskType.GENERATE_VIDEO, payload)
        background_tasks.add_task(run_generate_video_task, task.id)
        return GenerateVideoResponse(
            task_id=task.id,
            status=task.status,
            message="Task created successfully. Results will be sent to the callback URL when ready."
        )
    except Exception as e:
        # Log the exception details here
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate task: {e}"
        )

# The /upload-yt-video endpoint below is being removed as its functionality
# is consolidated into app/routers/youtube_videos.py with the path /youtube/videos/upload.
# @router.post(
#     "/upload-yt-video",
# ... (rest of the function definition)
# Ensure there are no trailing empty lines if this was the last function. 