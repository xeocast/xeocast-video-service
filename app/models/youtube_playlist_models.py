from pydantic import BaseModel, Field
from typing import Optional, List

class PlaylistSnippet(BaseModel):
    title: str = Field(..., min_length=1, max_length=150, description="The playlist's title.")
    description: Optional[str] = Field(None, max_length=5000, description="The playlist's description.")
    # tags: Optional[List[str]] = Field(None, description="A list of keyword tags associated with the playlist.") # Not directly available at top level of snippet for insert/update
    # defaultLanguage: Optional[str] = Field(None, description="The language of the playlist's default metadata.") # Same as above

class PlaylistStatus(BaseModel):
    privacyStatus: str = Field("private", description="The playlist's privacy status.", pattern="^(private|public|unlisted)$")

class Playlist(BaseModel):
    snippet: PlaylistSnippet
    status: Optional[PlaylistStatus] = None # Status is optional on create, defaults to private if not sent. Required on update.

class PlaylistCreateRequest(BaseModel):
    youtube_channel_id: str = Field(..., description="The YouTube channel ID to identify the saved credentials.")
    title: str = Field(..., min_length=1, max_length=150, description="The playlist's title.")
    description: Optional[str] = Field(None, max_length=5000, description="The playlist's description.")
    privacy_status: str = Field("private", description="The playlist's privacy status (private, public, or unlisted).", pattern="^(private|public|unlisted)$")

class PlaylistUpdateRequest(BaseModel):
    youtube_channel_id: str = Field(..., description="The YouTube channel ID to identify the saved credentials.")
    title: Optional[str] = Field(None, min_length=1, max_length=150, description="The new title for the playlist.")
    description: Optional[str] = Field(None, max_length=5000, description="The new description for the playlist.")
    privacy_status: Optional[str] = Field(None, description="The new privacy status (private, public, or unlisted).", pattern="^(private|public|unlisted)$")
    # We could add tags or default language if needed here as well, but they are part of snippet or localizations.

class PlaylistResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    privacy_status: str
    channel_id: str
    item_count: Optional[int] = None # From contentDetails
    published_at: Optional[str] = None # from snippet

class PlaylistItem(BaseModel): # For listing items within a playlist, if needed later. Not for this CRUD.
    pass

class ListPlaylistsResponse(BaseModel):
    items: List[PlaylistResponse]
    next_page_token: Optional[str] = None
    prev_page_token: Optional[str] = None
    page_info: Optional[dict] = None # Contains totalResults, resultsPerPage 