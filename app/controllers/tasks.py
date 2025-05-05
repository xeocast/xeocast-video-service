from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.models.api_models import TaskMetadata, ErrorResponse
from app.services.task_service import task_service
from app.utils.dependencies import get_api_key

router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
    dependencies=[Depends(get_api_key)],
    responses={404: {"model": ErrorResponse, "description": "Task not found"}},
)

@router.get(
    "/",
    response_model=List[TaskMetadata],
    summary="Get All Tasks",
    description="Retrieves metadata for all tasks known to the service."
)
async def get_all_tasks():
    """Retrieves metadata for all tasks."""
    tasks = task_service.get_all_tasks()
    return tasks

@router.get(
    "/{task_id}",
    response_model=TaskMetadata,
    summary="Get Task Status",
    description="Retrieves metadata for a specific task using its unique ID."
)
async def get_task_status(task_id: str):
    """Retrieves metadata for a specific task."""
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {task_id}"
        )
    return task 