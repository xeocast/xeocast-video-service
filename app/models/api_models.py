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
    UPLOAD_YOUTUBE_VIDEO = "uploadYoutubeVideo"

class PrivacyStatus(str, Enum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"

# --- Base Models ---

class BaseTaskDetails(BaseModel):
    callback_url: HttpUrl

# --- Generate Video Specific Models ---

class GenerateVideoDetails(BaseTaskDetails):
    background_image_key: str
    audio_file_key: str
    output_bucket_key: str # Key where the generated video should be saved

class GenerateVideoResponse(BaseModel):
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    message: str

# --- Publish Video Specific Models ---

class UploadYoutubeVideoDetails(BaseTaskDetails):
    video_url: HttpUrl
    youtube_api_key: str
    youtube_video_title: str
    youtube_video_description: str
    youtube_video_tags: str # Keep as string, split later if needed
    youtube_video_thumbnail_url: HttpUrl
    youtube_video_playlist_id: str

class UploadYoutubeVideoResponse(BaseModel):
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

class GenerateVideoCallbackPayload(BaseModel):
    taskId: str
    status: Literal["completed", "error"]
    video_bucket_key: Optional[str] = None # Key for the video in R2 bucket
    error: Optional[str] = None

class YouTubeUploadCallbackPayload(BaseModel):
    taskId: str
    status: Literal["completed", "error"]
    youtube_video_url: Optional[HttpUrl] = None # URL of the uploaded YouTube video
    youtube_video_id: Optional[str] = None # ID of the uploaded YouTube video
    error: Optional[str] = None

# --- Test Callback Models ---

class TestCallbackResponse(BaseModel):
    received: bool
    error: Optional[str] = None

# --- Test Callback Payload Model ---
class TestCallbackPayload(BaseModel):
    data: Dict[str, Any]

# --- Error Models ---

class ErrorResponse(BaseModel):
    error: str
    message: Optional[str] = None

# --- Health Check Models ---
class HealthResponse(BaseModel):
    status: str

# --- YouTube Video Upload Request Model ---
class YouTubeVideoUploadRequest(BaseModel):
    callback_url: HttpUrl = Field(..., description="URL to send the callback to after processing.")
    youtube_channel_id: str = Field(..., description="YouTube channel ID for retrieving the access token.")
    video_file_key: str = Field(..., description="Key of the video file in the R2 bucket.")
    video_thumbnail_key: Optional[str] = Field(None, description="Key of the video thumbnail in the R2 bucket.")
    title: str = Field(..., max_length=100, description="Title of the YouTube video.")
    description: str = Field(..., max_length=5000, description="Description of the YouTube video.")
    category_id: str = Field(..., description="Category ID of the YouTube video.")
    tags: List[str] = Field(..., max_items=50, description="List of tags for the YouTube video.")
    privacy_status: PrivacyStatus = Field(PrivacyStatus.PRIVATE, description="Privacy status of the YouTube video.")
    publish_at: Optional[datetime] = Field(None, description="Scheduled date and time to publish the video (ISO 8601 format).")
    playlist_id: Optional[str] = Field(None, description="YouTube playlist ID to add the video to.")
    first_comment: Optional[str] = Field(None, description="Optional first comment to add and pin to the video.")

class CreateTaskResponse(BaseModel):
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    message: str 