import logging
import os
from pathlib import Path
import httpx # For sending callbacks
from googleapiclient.discovery import build # Needs google-api-python-client
from googleapiclient.http import MediaFileUpload # Needs google-api-python-client
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest # Added import
from pydantic import HttpUrl # Ensure HttpUrl is imported if used in payload

from app.models.api_models import YouTubeVideoUploadRequest, TaskStatus, YouTubeUploadCallbackPayload # Changed from CallbackPayload
from app.services.task_service import task_service
from app.services.youtube_oauth_service import youtube_oauth_service
from app.services.r2_service import r2_service # Make sure r2_service is imported
from app.services.callback_service import callback_service # Added import
from app.models.settings import settings

logger = logging.getLogger(__name__)

class YouTubeVideoService:
    async def _send_callback(self, url: str, payload: YouTubeUploadCallbackPayload): # Changed payload type
        # try:
        #     async with httpx.AsyncClient(timeout=settings.CALLBACK_TIMEOUT_SECONDS) as client:
        #         response = await client.post(url, json=payload.model_dump())
        #         response.raise_for_status() # Raise an exception for bad status codes
        #         logger.info(f"Sent callback for task {payload.taskId} to {url}. Status: {response.status_code}")
        # except httpx.RequestError as e:
        #     logger.error(f"Error sending callback for task {payload.taskId} to {url}: {e}")
        # except Exception as e:
        #     logger.error(f"Unexpected error sending callback for task {payload.taskId} to {url}: {e}")
        # Use the centralized callback_service
        await callback_service.send_callback(url, payload)

    async def process_upload_task(self, task_id: str):
        logger.info(f"Starting YouTube upload process for task: {task_id}")
        task = task_service.get_task(task_id)

        if not task or not isinstance(task.details, dict):
            logger.error(f"Task {task_id} not found or details are not in expected format.")
            # Cannot send callback as we don't have details or callback_url
            return

        try:
            upload_details = YouTubeVideoUploadRequest(**task.details)
        except Exception as e:
            logger.error(f"Failed to parse task details for {task_id}: {e}")
            task_service.set_task_error(task_id, f"Invalid task details: {e}")
            # Cannot reliably send callback if details (containing callback_url) are unparsable
            return
            
        callback_url_str = str(upload_details.callback_url)
        video_file_path: Optional[Path] = None
        thumbnail_file_path: Optional[Path] = None
        video_id: Optional[str] = None # Ensure video_id is defined in this scope

        try:
            task_service.set_task_processing(task_id)
            logger.info(f"Task {task_id} set to PROCESSING.")

            # 1. Get YouTube Credentials
            credentials = youtube_oauth_service.load_credentials(upload_details.youtube_channel_id)
            if not credentials:
                raise ValueError(f"Could not retrieve or load YouTube credentials for channel {upload_details.youtube_channel_id}. Please re-authenticate.")
            if credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(GoogleAuthRequest()) # Use GoogleAuthRequest
                    logger.info(f"Refreshed YouTube credentials for channel {upload_details.youtube_channel_id}")
                    youtube_oauth_service.save_credentials(upload_details.youtube_channel_id, credentials) # Save refreshed credentials
                except RefreshError as re:
                    logger.error(f"Failed to refresh YouTube token for channel {upload_details.youtube_channel_id}: {re}")
                    raise ValueError(f"Token refresh failed for channel {upload_details.youtube_channel_id}. Please re-authenticate.")

            # 2. Determine R2 bucket and download files
            # Bucket name depends on environment, ensure settings has R2_VIDEO_OUTPUT_BUCKET_PROD and R2_VIDEO_OUTPUT_BUCKET_DEV
            # This logic assumes your settings structure has a general R2_VIDEO_OUTPUT_BUCKET that is set based on ENV.
            # If not, you might need settings.R2_VIDEO_OUTPUT_BUCKET_PROD/DEV directly.
            # For this example, let's assume settings.R2_VIDEO_OUTPUT_BUCKET holds the correct one.
            if not settings.R2_VIDEO_OUTPUT_BUCKET:
                 raise ValueError("R2_VIDEO_OUTPUT_BUCKET is not configured in settings.")
            r2_bucket = settings.R2_VIDEO_OUTPUT_BUCKET

            # Create temporary directory for downloads if it doesn't exist
            temp_download_dir = settings.TMP_DIR / "yt_uploads" / task_id
            temp_download_dir.mkdir(parents=True, exist_ok=True)

            video_file_path = temp_download_dir / upload_details.video_file_key.split('/')[-1] # Get filename from key
            logger.info(f"Downloading video '{upload_details.video_file_key}' from bucket '{r2_bucket}' to '{video_file_path}'")
            r2_service.download_file(r2_bucket, upload_details.video_file_key, str(video_file_path)) # Ensure path is string

            if upload_details.video_thumbnail_key:
                thumbnail_file_path = temp_download_dir / upload_details.video_thumbnail_key.split('/')[-1]
                logger.info(f"Downloading thumbnail '{upload_details.video_thumbnail_key}' from bucket '{r2_bucket}' to '{thumbnail_file_path}'")
                r2_service.download_file(r2_bucket, upload_details.video_thumbnail_key, str(thumbnail_file_path)) # Ensure path is string
            else:
                thumbnail_file_path = None
                logger.info(f"No thumbnail key provided for task {task_id}. Skipping thumbnail download.")

            # 3. Initialize YouTube API Client
            youtube_api = build("youtube", "v3", credentials=credentials, static_discovery=False) # static_discovery=False for dynamic envs
            logger.info(f"Initialized YouTube API client for task {task_id}.")

            # 4. Upload Video
            media_body = MediaFileUpload(str(video_file_path), chunksize=-1, resumable=True)
            request_body = {
                "snippet": {
                    "title": upload_details.title,
                    "description": upload_details.description,
                    "tags": upload_details.tags,
                    "category_id": upload_details.category_id,
                    # "defaultLanguage": "en", # Consider making configurable or detecting
                    # "defaultAudioLanguage": "en" # Consider making configurable or detecting
                },
                "status": {
                    "privacyStatus": upload_details.privacy_status.value,
                    "selfDeclaredMadeForKids": False, # Defaulting to False, make configurable if necessary
                }
            }
            if upload_details.publish_at:
                # Ensure datetime is in ISO 8601 format with Z for UTC if not timezone-aware
                request_body["status"]["publishAt"] = upload_details.publish_at.isoformat()

            response_upload = youtube_api.videos().insert(
                part=",".join(request_body.keys()),
                body=request_body,
                media_body=media_body
            ).execute()
            video_id = response_upload.get("id")
            if not video_id:
                raise ValueError("YouTube API did not return a video ID after upload.")
            logger.info(f"Video {video_id} uploaded successfully for task {task_id}.")

            # 5. Set Thumbnail
            if thumbnail_file_path and thumbnail_file_path.exists(): # Check if thumbnail was downloaded and exists
                youtube_api.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumbnail_file_path))
                ).execute()
                logger.info(f"Thumbnail set for video {video_id} for task {task_id}.")
            elif upload_details.video_thumbnail_key: # Log if key was provided but file is missing (shouldn't happen if download worked)
                logger.warning(f"Thumbnail key was provided for video {video_id} but file not found at {thumbnail_file_path}. Skipping thumbnail set.")
            else: # No key provided, so no thumbnail to set
                logger.info(f"No thumbnail to set for video {video_id} as no key was provided.")

            # 6. Add to Playlist (if playlist_id is provided)
            if video_id and upload_details.playlist_id:
                youtube_api.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": upload_details.playlist_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id
                            }
                        }
                    }
                ).execute()
                logger.info(f"Video {video_id} added to playlist {upload_details.playlist_id} for task {task_id}.")

            # 7. Add First Comment (if first_comment is provided)
            comment_id_to_pin = None
            if video_id and upload_details.first_comment:
                comment_thread_response = youtube_api.commentThreads().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "videoId": video_id,
                            "topLevelComment": {
                                "snippet": {
                                    "textOriginal": upload_details.first_comment
                                }
                            }
                        }
                    }
                ).execute()
                # The actual comment ID is in the topLevelComment object
                comment_id_to_pin = comment_thread_response.get("snippet", {}).get("topLevelComment", {}).get("id")
                if comment_id_to_pin:
                    logger.info(f"Comment {comment_id_to_pin} added to video {video_id}.")
                    # Ensure the comment is published before attempting to pin
                    # Pinning a comment programmatically is not directly supported by the YouTube Data API v3 in a simple way.
                    # It usually requires the channel owner's credentials and specific permissions.
                    # The common practice is to ensure the comment is published and then pin it via YouTube Studio if the API doesn't allow it.
                    try:
                        youtube_api.comments().setModerationStatus(
                            id=comment_id_to_pin,
                            moderationStatus='published' # Ensure comment is visible
                        ).execute()
                        logger.info(f"Set moderation status to 'published' for comment {comment_id_to_pin}.")

                        # The YouTube Data API v3 does not offer a direct method to "pin" a comment via a simple flag.
                        # Pinning is typically done through the YouTube Studio interface.
                        # The following commented-out code represents attempts that are not supported or are unreliable.
                        # youtube_api.comments().update(
                        #     part='snippet', # or 'id' or 'pinningDetails' - unclear from official docs
                        #     body={
                        #         "id": comment_id_to_pin,
                        #         "snippet": { # Snippet might be required if 'snippet' is in part
                        #             # "videoId": video_id, # videoId might be required contextually
                        #         },
                        #         # Attempting to use a hypothetical 'pinningDetails' or similar
                        #         # "pinningDetails": { "isPinned": True } # This structure is speculative
                        #         # "isPinned": True # Another speculative attempt
                        #     }
                        # ).execute()
                        # logger.info(f"Attempted to pin comment {comment_id_to_pin} on video {video_id}.")
                        logger.info(f"Comment {comment_id_to_pin} added and status set to published. Pinning typically requires YouTube Studio or specific advanced API usage if available and may not be feasible with standard permissions.")
                    except Exception as e_pin:
                        logger.error(f"Could not set moderation status or attempt pinning for comment {comment_id_to_pin} on video {video_id}: {e_pin}")
                else:
                    logger.warning(f"Could not get comment ID to pin for video {video_id}.")

            youtube_video_url = f"https://www.youtube.com/watch?v={video_id}"
            task_service.set_task_completed(task_id, result={"youtube_video_id": video_id, "youtube_video_url": youtube_video_url, "comment_id": comment_id_to_pin})
            logger.info(f"Task {task_id} completed successfully. YouTube Video ID: {video_id}")
            
            payload = YouTubeUploadCallbackPayload( # Changed here
                taskId=task_id,
                status="completed",
                youtube_video_id=video_id, # Added this field
                youtube_video_url=HttpUrl(youtube_video_url) # Ensured HttpUrl, was video_url
            )
            await self._send_callback(callback_url_str, payload)

        except Exception as e:
            error_message = f"Error processing YouTube upload for task {task_id}: {e}"
            logger.error(error_message, exc_info=True)
            task_service.set_task_error(task_id, error_message)
            
            payload = YouTubeUploadCallbackPayload( # Changed here
                taskId=task_id,
                status="error",
                error=error_message
            )
            await self._send_callback(callback_url_str, payload)

        finally:
            # Clean up downloaded files
            if video_file_path and video_file_path.exists(): # Always try to clean up video
                try:
                    os.remove(video_file_path)
                    logger.info(f"Cleaned up temporary file: {video_file_path}")
                except OSError as e_os:
                    logger.error(f"Error deleting temporary file {video_file_path}: {e_os}")
            
            if thumbnail_file_path and thumbnail_file_path.exists(): # Only try to clean up thumbnail if it was processed
                try:
                    os.remove(thumbnail_file_path)
                    logger.info(f"Cleaned up temporary file: {thumbnail_file_path}")
                except OSError as e_os:
                    logger.error(f"Error deleting temporary file {thumbnail_file_path}: {e_os}")
            
            # Clean up task-specific directory if empty
            if 'temp_download_dir' in locals() and temp_download_dir.exists() and not any(temp_download_dir.iterdir()):
                try:
                    temp_download_dir.rmdir()
                    logger.info(f"Cleaned up temporary directory: {temp_download_dir}")
                except OSError as e_os:
                    logger.error(f"Error deleting temporary directory {temp_download_dir}: {e_os}")


# Singleton instance
youtube_video_service = YouTubeVideoService() 