from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class GetYoutubeAuthUrlRequest(BaseModel):
    youtube_channel_id: str
    client_secret_filename: str # This will be the key for the R2 object

class GetYoutubeAuthUrlResponse(BaseModel):
    authorization_url: str

# New models for YouTube video details
class YouTubeVideoStatus(BaseModel):
    privacy_status: str = Field(..., alias="privacyStatus")
    upload_status: Optional[str] = Field(None, alias="uploadStatus")
    failure_reason: Optional[str] = Field(None, alias="failureReason")
    rejection_reason: Optional[str] = Field(None, alias="rejectionReason")
    publish_at: Optional[datetime] = Field(None, alias="publishAt") # For videos scheduled to be published

class YouTubeVideoSnippet(BaseModel):
    published_at: datetime = Field(..., alias="publishedAt")
    channel_id: str = Field(..., alias="channelId")
    title: str
    description: str
    channel_title: str = Field(..., alias="channelTitle")
    # Add other relevant snippet fields if needed, like thumbnails

class YouTubeVideoDetailsResponse(BaseModel):
    video_id: str
    title: str
    description: str
    published_at: datetime
    privacy_status: str
    upload_status: Optional[str] = None
    channel_id: str
    channel_title: str
    publish_at: Optional[datetime] = None # From status part if scheduled

class YouTubeVideoNotFoundResponse(BaseModel):
    error: str = "Video not found"
    video_id: str
    message: Optional[str] = None 