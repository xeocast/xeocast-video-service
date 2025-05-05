import logging
from pathlib import Path
from typing import Optional, List
import asyncio

# Google API Client Libraries
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
# Note: google-auth libraries are typically needed for OAuth, which is the standard
# for uploads. API Key might work for public data but usually not for uploads/modifications.
# We follow the design's 'youtube_api_key' parameter, but this might need changing to OAuth flow.

from app.models.api_models import PublishVideoDetails

logger = logging.getLogger(__name__)

# YouTube Upload constants
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]
DEFAULT_VIDEO_CATEGORY = "22" # See https://developers.google.com/youtube/v3/docs/videoCategories/list
DEFAULT_PRIVACY_STATUS = "private" # Options: 'public', 'private', 'unlisted'

class YouTubeService:

    async def upload_video(
        self,
        video_path: Path,
        details: PublishVideoDetails
    ) -> Optional[str]:
        """Uploads the video to YouTube using the provided details and API key."""

        logger.info(f"Attempting YouTube upload for video: {video_path}, title: {details.youtube_video_title}")
        if not video_path.exists():
             logger.error(f"YouTube Upload Error: Video file not found at {video_path}")
             raise FileNotFoundError(f"Video file not found: {video_path}")

        # API Key Authentication (as per design spec)
        # WARNING: Video uploads generally require OAuth 2.0. Using only an API key
        # might restrict functionality or fail depending on API policies.
        # Consider implementing OAuth 2.0 flow if uploads fail with API key.
        try:
            youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=details.youtube_api_key)

            video_tags = [tag.strip() for tag in details.youtube_video_tags.split(',') if tag.strip()] if details.youtube_video_tags else []

            body = {
                "snippet": {
                    "title": details.youtube_video_title,
                    "description": details.youtube_video_description,
                    "tags": video_tags,
                    "categoryId": DEFAULT_VIDEO_CATEGORY # Consider making this configurable
                },
                "status": {
                    "privacyStatus": DEFAULT_PRIVACY_STATUS # Consider making this configurable
                }
            }

            logger.debug(f"YouTube API request body: {body}")

            # Call the API to upload the video.
            media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)

            logger.info(f"Initiating YouTube video insert request for {video_path.name}")
            request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media
            )

            # Execute the request (potentially long-running)
            # Run synchronous Google API call in a thread pool executor
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, request.execute)

            video_id = response.get('id')
            logger.info(f"Successfully uploaded video to YouTube. Video ID: {video_id}")

            # --- Optional: Add to Playlist --- #
            if video_id and details.youtube_video_playlist_id:
                await self._add_video_to_playlist(youtube, video_id, details.youtube_video_playlist_id)

            # --- Optional: Set Thumbnail (More complex, requires separate request) --- #
            # if video_id and details.youtube_video_thumbnail_url:
            #    logger.warning("Setting YouTube thumbnail from URL is not implemented in this version.")
            #    # Requires downloading the thumbnail and using youtube.thumbnails().set() with media_body

            return video_id

        except HttpError as e:
            logger.error(f"An HTTP error {e.resp.status} occurred during YouTube upload: {e.content}", exc_info=True)
            raise RuntimeError(f"YouTube API HTTP error: {e.resp.status} - {e.content}") from e
        except Exception as e:
            logger.error(f"Failed to upload video to YouTube: {e}", exc_info=True)
            # Catch specific auth errors if possible (e.g., google.auth.exceptions.RefreshError for OAuth)
            raise RuntimeError(f"YouTube API upload failed: {e}") from e

    async def _add_video_to_playlist(self, youtube_client, video_id: str, playlist_id: str):
        """Adds a video to a specified YouTube playlist."""
        try:
            logger.info(f"Attempting to add video {video_id} to playlist {playlist_id}")
            body = {
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id
                    }
                }
            }
            request = youtube_client.playlistItems().insert(
                part="snippet",
                body=body
            )
            # Run synchronous Google API call in a thread pool executor
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, request.execute)
            logger.info(f"Successfully added video {video_id} to playlist {playlist_id}")
        except HttpError as e:
            # Log error but don't fail the entire upload process just for playlist add failure
            logger.error(f"Failed to add video {video_id} to playlist {playlist_id}: {e.content}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error adding video {video_id} to playlist {playlist_id}: {e}", exc_info=True)


# Singleton instance
youtube_service = YouTubeService() 