from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status, Query
from pydantic import HttpUrl
from typing import Optional

from app.models.api_models import (
    GenerateVideoResponse, PublishVideoResponse,
    ErrorResponse, TaskType,
    GenerateVideoDetails, PublishVideoDetails
)
from app.services.task_service import task_service
from app.utils.dependencies import get_api_key
from app.utils.background_tasks import run_generate_video_task, run_publish_video_task

router = APIRouter(
    tags=["Video"],
    dependencies=[Depends(get_api_key)],
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)

@router.post(
    "/generate-video",
    response_model=GenerateVideoResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate Video",
    description="Initiates an asynchronous task to generate a video from a background image and an audio file."
)
async def generate_video(
    background_tasks: BackgroundTasks,
    background_image_url: HttpUrl = Query(..., description="The full URL of the background image file."),
    audio_file_url: HttpUrl = Query(..., description="The full URL of the audio file."),
    callback_url: HttpUrl = Query(..., description="The URL where the service will send results."),
    youtube_api_key: Optional[str] = Query(None, description="Optional YouTube API key for uploading."),
    youtube_video_title: Optional[str] = Query(None, description="Title for the YouTube video."),
    youtube_video_description: Optional[str] = Query(None, description="Description for the YouTube video."),
    youtube_video_tags: Optional[str] = Query(None, description="Comma-separated tags for the YouTube video."),
    youtube_video_thumbnail_url: Optional[HttpUrl] = Query(None, description="URL for the YouTube video thumbnail."),
    youtube_video_playlist_id: Optional[str] = Query(None, description="YouTube playlist ID to add the video to.")
):
    """Endpoint to start video generation."""
    details = GenerateVideoDetails(
        background_image_url=background_image_url,
        audio_file_url=audio_file_url,
        callback_url=callback_url,
        youtube_api_key=youtube_api_key,
        youtube_video_title=youtube_video_title,
        youtube_video_description=youtube_video_description,
        youtube_video_tags=youtube_video_tags,
        youtube_video_thumbnail_url=youtube_video_thumbnail_url,
        youtube_video_playlist_id=youtube_video_playlist_id
    )

    try:
        task = task_service.create_task(TaskType.GENERATE_VIDEO, details)
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

@router.post(
    "/publish-video",
    response_model=PublishVideoResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Publish Video to YouTube",
    description="Publishes a pre-existing video to YouTube via API."
)
async def publish_video(
    background_tasks: BackgroundTasks,
    video_url: HttpUrl = Query(..., description="The full URL of the video file to publish."),
    callback_url: HttpUrl = Query(..., description="The URL where the service will send results."),
    youtube_api_key: str = Query(..., description="YouTube API key for uploading."),
    youtube_video_title: str = Query(..., description="Title for the YouTube video."),
    youtube_video_description: str = Query(..., description="Description for the YouTube video."),
    youtube_video_tags: str = Query(..., description="Comma-separated tags for the YouTube video."),
    youtube_video_thumbnail_url: HttpUrl = Query(..., description="URL for the YouTube video thumbnail."),
    youtube_video_playlist_id: str = Query(..., description="YouTube playlist ID to add the video to.")
):
    """Endpoint to start video publishing to YouTube."""
    details = PublishVideoDetails(
        video_url=video_url,
        callback_url=callback_url,
        youtube_api_key=youtube_api_key,
        youtube_video_title=youtube_video_title,
        youtube_video_description=youtube_video_description,
        youtube_video_tags=youtube_video_tags,
        youtube_video_thumbnail_url=youtube_video_thumbnail_url,
        youtube_video_playlist_id=youtube_video_playlist_id
    )

    try:
        task = task_service.create_task(TaskType.PUBLISH_VIDEO, details)
        background_tasks.add_task(run_publish_video_task, task.id)
        return PublishVideoResponse(
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