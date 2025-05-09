import logging
import os
from pathlib import Path
import httpx # For sending callbacks
from googleapiclient.discovery import build # Needs google-api-python-client
from googleapiclient.http import MediaFileUpload # Needs google-api-python-client
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError

from app.models.api_models import YouTubeVideoUploadRequest, TaskStatus, CallbackPayload
from app.services.task_service import task_service
from app.services.youtube_oauth_service import youtube_oauth_service
from app.services.r2_service import r2_service # Make sure r2_service is imported
from app.models.settings import settings

logger = logging.getLogger(__name__)

class YouTubeVideoService:
    async def _send_callback(self, url: str, payload: CallbackPayload):
        try:
            async with httpx.AsyncClient(timeout=settings.CALLBACK_TIMEOUT_SECONDS) as client:
                response = await client.post(url, json=payload.model_dump())
                response.raise_for_status() # Raise an exception for bad status codes
                logger.info(f"Sent callback for task {payload.taskId} to {url}. Status: {response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Error sending callback for task {payload.taskId} to {url}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending callback for task {payload.taskId} to {url}: {e}")

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

        try:
            task_service.set_task_processing(task_id)
            logger.info(f"Task {task_id} set to PROCESSING.")

            # 1. Get YouTube Credentials
            credentials = youtube_oauth_service.load_credentials(upload_details.youtube_channel_id)
            if not credentials:
                raise ValueError(f"Could not retrieve or load YouTube credentials for channel {upload_details.youtube_channel_id}. Please re-authenticate.")
            if credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(httpx.Request()) # Use httpx.Request for sync refresh context if needed by google-auth
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
            thumbnail_file_path = temp_download_dir / upload_details.video_thumbnail_key.split('/')[-1]

            logger.info(f"Downloading video '{upload_details.video_file_key}' from bucket '{r2_bucket}' to '{video_file_path}'")
            r2_service.download_file(r2_bucket, upload_details.video_file_key, video_file_path)
            logger.info(f"Downloading thumbnail '{upload_details.video_thumbnail_key}' from bucket '{r2_bucket}' to '{thumbnail_file_path}'")
            r2_service.download_file(r2_bucket, upload_details.video_thumbnail_key, thumbnail_file_path)

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
                    "categoryId": upload_details.categoryId,
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
            youtube_api.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_file_path))
            ).execute()
            logger.info(f"Thumbnail set for video {video_id} for task {task_id}.")

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
                    # Pinning the comment: set moderationStatus to 'published' (for visibility) 
                    # and then call comments().update() with the 'pin' action.
                    # Note: Pinning requires the channel owner's credentials and that the video is public or unlisted.
                    # First, ensure comment is published (usually by default)
                    # youtube_api.comments().setModerationStatus(
                    #     id=comment_id_to_pin,
                    #     moderationStatus='published' 
                    # ).execute()
                    # Then pin:
                    # youtube_api.comments().update(
                    #     part='snippet',
                    #     body={
                    #         "id": comment_id_to_pin,
                    #         "snippet": {
                    #             "videoId": video_id, # Required by some API versions for comment update context
                    #             "parentId": comment_id_to_pin, # Incorrect usage, pinning is a property of comment not parent
                    #             "canPin": True # This is a read-only property usually
                    #         },
                    #         "pinningDetails": { # This might be part of a different method or not directly available.
                    #             "pinned": True
                    #         }
                    #     }
                    # ).execute()
                    # Simpler approach for pinning: The YouTube API for pinning comments is tricky.
                    # The `comments.update` method doesn't directly support a `pinned` flag.
                    # Pinning typically involves setting the moderation status or a specific action if available.
                    # For now, we just add the comment. Pinning might need manual intervention or a more specific API call if one exists for this purpose.
                    # It often requires setting the comment's `moderationStatus` to `published` and then, if the API supports, a `pin` action.
                    # The `comments.pin` method was part of a previous API version. Modern way is more complex or UI-driven.
                    # Let's assume for now, adding it is sufficient and pinning is a separate concern if API doesn't directly support.
                    logger.info(f"Comment {comment_id_to_pin} added. Pinning may require YouTube Studio or specific permissions.")
                else:
                    logger.warning(f"Could not get comment ID to pin for video {video_id}.")

            youtube_video_url = f"https://www.youtube.com/watch?v={video_id}"
            task_service.set_task_completed(task_id, result={"youtube_video_id": video_id, "youtube_video_url": youtube_video_url, "comment_id": comment_id_to_pin})
            logger.info(f"Task {task_id} completed successfully. YouTube Video ID: {video_id}")
            
            payload = CallbackPayload(taskId=task_id, status="completed", video_url=youtube_video_url)
            await self._send_callback(callback_url_str, payload)

        except Exception as e:
            error_message = f"Error processing YouTube upload for task {task_id}: {e}"
            logger.error(error_message, exc_info=True)
            task_service.set_task_error(task_id, error_message)
            
            payload = CallbackPayload(taskId=task_id, status="error", error=error_message)
            await self._send_callback(callback_url_str, payload)

        finally:
            # Clean up downloaded files
            for file_p in [video_file_path, thumbnail_file_path]:
                if file_p and file_p.exists():
                    try:
                        os.remove(file_p)
                        logger.info(f"Cleaned up temporary file: {file_p}")
                    except OSError as e_os:
                        logger.error(f"Error deleting temporary file {file_p}: {e_os}")
            # Clean up task-specific directory if empty
            if 'temp_download_dir' in locals() and temp_download_dir.exists() and not any(temp_download_dir.iterdir()):
                try:
                    temp_download_dir.rmdir()
                    logger.info(f"Cleaned up temporary directory: {temp_download_dir}")
                except OSError as e_os:
                    logger.error(f"Error deleting temporary directory {temp_download_dir}: {e_os}")


# Singleton instance
youtube_video_service = YouTubeVideoService() 