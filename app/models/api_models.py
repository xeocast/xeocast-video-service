from pydantic import BaseModel, Field, HttpUrl, RootModel
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
import uuid
from enum import Enum

# --- Enums ---

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"

class TaskType(str, Enum):
    GENERATE_VIDEO = "generateVideo"
    PUBLISH_VIDEO = "publishVideo"

# --- Base Models ---

class BaseTaskDetails(BaseModel):
    callback_url: HttpUrl

# --- Generate Video Specific Models ---

class GenerateVideoDetails(BaseTaskDetails):
    background_image_url: HttpUrl
    audio_file_url: HttpUrl
    youtube_api_key: Optional[str] = None
    youtube_video_title: Optional[str] = None
    youtube_video_description: Optional[str] = None
    youtube_video_tags: Optional[str] = None # Keep as string, split later if needed
    youtube_video_thumbnail_url: Optional[HttpUrl] = None
    youtube_video_playlist_id: Optional[str] = None

class GenerateVideoResponse(BaseModel):
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    message: str

# --- Publish Video Specific Models ---

class PublishVideoDetails(BaseTaskDetails):
    video_url: HttpUrl
    youtube_api_key: str
    youtube_video_title: str
    youtube_video_description: str
    youtube_video_tags: str # Keep as string, split later if needed
    youtube_video_thumbnail_url: HttpUrl
    youtube_video_playlist_id: str

class PublishVideoResponse(BaseModel):
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    message: str

# --- Task Metadata Models ---

class TaskMetadata(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    type: TaskType
    details: Dict[str, Any] # Store specific details based on type
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None # Store results like video URL

class GetAllTasksResponse(RootModel[List[TaskMetadata]]):
    """Response model for retrieving a list of all tasks."""
    pass

# --- Callback Models ---

class CallbackPayload(BaseModel):
    taskId: str
    status: Literal["completed", "error"]
    video_url: Optional[str] = None # URL with signature
    video_signature: Optional[str] = None # Kept for compatibility with design, though signature is in URL
    error: Optional[str] = None

# --- Test Callback Models ---

class TestCallbackResponse(BaseModel):
    received: bool
    error: Optional[str] = None

# --- Error Models ---

class ErrorResponse(BaseModel):
    error: str
    message: Optional[str] = None

# --- Health Check Models ---
class HealthResponse(BaseModel):
    status: str 