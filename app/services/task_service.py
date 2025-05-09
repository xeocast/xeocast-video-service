from typing import Dict, List, Optional
from datetime import datetime
import threading

from app.models.api_models import TaskMetadata, TaskStatus, TaskType, GenerateVideoDetails, UploadYoutubeVideoDetails


class TaskService:
    def __init__(self):
        self._tasks: Dict[str, TaskMetadata] = {}
        self._lock = threading.Lock() # Protect access to _tasks

    def create_task(
        self,
        task_type: TaskType,
        details: GenerateVideoDetails | UploadYoutubeVideoDetails
    ) -> TaskMetadata:
        """Creates a new task and stores it."""
        with self._lock:
            task = TaskMetadata(type=task_type, details=details.model_dump(exclude_unset=True))
            self._tasks[task.id] = task
            return task

    def get_task(self, task_id: str) -> Optional[TaskMetadata]:
        """Retrieves a task by its ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[TaskMetadata]:
        """Retrieves all tasks."""
        with self._lock:
            return list(self._tasks.values())

    def update_task_status(self, task_id: str, status: TaskStatus, error: Optional[str] = None) -> Optional[TaskMetadata]:
        """Updates the status and optionally the error message of a task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = status
                task.error = error
                task.updated_at = datetime.utcnow()
                return task
            return None

    def update_task_result(self, task_id: str, result: Dict) -> Optional[TaskMetadata]:
        """Adds results to a completed task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.COMPLETED:
                task.result = result
                task.updated_at = datetime.utcnow()
                return task
            return None

    def set_task_processing(self, task_id: str) -> Optional[TaskMetadata]:
        """Convenience method to set task status to processing."""
        return self.update_task_status(task_id, TaskStatus.PROCESSING)

    def set_task_completed(self, task_id: str, result: Dict) -> Optional[TaskMetadata]:
        """Convenience method to set task status to completed and add result."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.COMPLETED
                task.error = None  # Explicitly clear any previous error
                task.result = result
                task.updated_at = datetime.utcnow()
            return task

    def set_task_error(self, task_id: str, error_message: str) -> Optional[TaskMetadata]:
        """Convenience method to set task status to error."""
        return self.update_task_status(task_id, TaskStatus.ERROR, error=error_message)

    def remove_task(self, task_id: str) -> bool:
        """Removes a task from the store."""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False

# Singleton instance
task_service = TaskService() 