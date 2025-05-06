from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status, Query, Body
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
    payload: GenerateVideoDetails = Body(...)
):
    """Endpoint to start video generation."""
    try:
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

@router.post(
    "/publish-video",
    response_model=PublishVideoResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Publish Video to YouTube",
    description="Publishes a pre-existing video to YouTube via API."
)
async def publish_video(
    background_tasks: BackgroundTasks,
    payload: PublishVideoDetails = Body(...)
):
    """Endpoint to start video publishing to YouTube."""
    try:
        task = task_service.create_task(TaskType.PUBLISH_VIDEO, payload)
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