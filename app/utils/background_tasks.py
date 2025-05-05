import logging
import asyncio
from pathlib import Path
from typing import Optional

from app.models.api_models import TaskMetadata, TaskStatus, GenerateVideoDetails, PublishVideoDetails, CallbackPayload
from app.services.task_service import task_service
from app.services.video_service import video_service
from app.services.file_downloader import file_downloader_service
from app.services.callback_service import callback_service
from app.services.signature_service import signature_service
from app.services.youtube_service import youtube_service # Assuming placeholder exists
from app.models.settings import settings # Import settings

logger = logging.getLogger(__name__)

async def _send_final_callback(task: TaskMetadata, status: TaskStatus, video_path: Optional[Path] = None, error_message: Optional[str] = None):
    """Helper function to construct and send the final callback."""
    video_url_with_signature = None
    signature = None # Keep for compatibility, even if only in URL
    if status == TaskStatus.COMPLETED and video_path:
        # Generate signed URL relative to where the static files will be served
        # Assuming static files served at /static/
        # The base_url should ideally come from request or config
        # Placeholder: Use relative path for now, signing logic needs the full URL context later
        relative_video_path = f"/static/{video_path.name}"
        # TODO: Determine the correct base URL for signing (e.g., from request or settings)
        # For now, let's assume a placeholder base URL. This MUST be configured correctly.
        base_url = "http://localhost:8000" # Placeholder - Needs to be dynamic or configurable
        # Use BASE_URL from settings
        base_url = settings.BASE_URL
        try:
            video_url_with_signature = signature_service.sign_url(base_url, relative_video_path)
            # Extract signature part if needed for the payload field (though redundant)
            # parsed = urlparse(video_url_with_signature)
            # query_params = parse_qs(parsed.query)
            # signature = query_params.get('signature', [None])[0]
            signature = "dummy_signature" # Placeholder

        except Exception as e:
            logger.error(f"Task {task.id}: Failed to sign video URL {relative_video_path}: {e}", exc_info=True)
            status = TaskStatus.ERROR
            error_message = f"Failed to sign video URL: {e}"
            video_url_with_signature = None
            signature = None

    callback_payload = CallbackPayload(
        taskId=task.id,
        status=status.value, # Use 'completed' or 'error' string
        video_url=video_url_with_signature,
        video_signature=signature, # Redundant if signature is in URL, but matches design
        error=error_message
    )

    # Update task one last time before sending callback
    if status == TaskStatus.COMPLETED:
        task_service.set_task_completed(task.id, result={'video_url': str(video_path), 'signed_url': video_url_with_signature})
    else:
        task_service.set_task_error(task.id, error_message or "Unknown error")

    # Send the callback
    await callback_service.send_callback(str(task.details['callback_url']), callback_payload)


async def run_generate_video_task(task_id: str):
    """Handles the asynchronous video generation process."""
    task = task_service.get_task(task_id)
    if not task or not isinstance(task.details, dict): # Check details is dict
        logger.error(f"Generate task {task_id}: Not found or details missing.")
        return

    # Type hint for clarity after check
    details: GenerateVideoDetails = GenerateVideoDetails(**task.details)

    task_service.set_task_processing(task_id)
    logger.info(f"Starting background task: Generate Video {task_id}")

    image_path_temp: Optional[Path] = None
    audio_path_temp: Optional[Path] = None
    output_video_path: Optional[Path] = None
    error_message: Optional[str] = None
    final_status: TaskStatus = TaskStatus.ERROR # Assume error until success

    try:
        # 1. Download files
        logger.info(f"Task {task_id}: Downloading background image from {details.background_image_url}")
        image_path_temp = await file_downloader_service.download_file(str(details.background_image_url), task_id)
        logger.info(f"Task {task_id}: Downloading audio file from {details.audio_file_url}")
        audio_path_temp = await file_downloader_service.download_file(str(details.audio_file_url), task_id)

        # 2. Generate Video filename
        output_filename = video_service._generate_video_filename(task_id)

        # 3. Generate Video (CPU-bound, consider running in a thread pool executor)
        logger.info(f"Task {task_id}: Starting video creation with MoviePy.")
        loop = asyncio.get_running_loop()
        output_video_path = await loop.run_in_executor(
            None, # Use default executor (ThreadPoolExecutor)
            video_service.create_video_from_image_audio,
            image_path_temp,
            audio_path_temp,
            output_filename
        )
        logger.info(f"Task {task_id}: Video created successfully at {output_video_path}")
        final_status = TaskStatus.COMPLETED

        # 4. (Optional) Upload to YouTube if API key provided
        if details.youtube_api_key and output_video_path:
            logger.info(f"Task {task_id}: YouTube API key provided, attempting upload.")
            try:
                # Prepare details for YouTube upload (might need adjustments)
                # Assuming GenerateVideoDetails contains needed fields for now
                publish_details = PublishVideoDetails(
                    video_url=details.background_image_url, # This isn't right, need video path or URL
                    callback_url=details.callback_url, # Not directly used by upload func
                    youtube_api_key=details.youtube_api_key,
                    youtube_video_title=details.youtube_video_title or "Untitled Video",
                    youtube_video_description=details.youtube_video_description or "",
                    youtube_video_tags=details.youtube_video_tags or "",
                    youtube_video_thumbnail_url=details.youtube_video_thumbnail_url, # Optional
                    youtube_video_playlist_id=details.youtube_video_playlist_id # Optional
                )
                youtube_video_id = await youtube_service.upload_video(output_video_path, publish_details)
                if youtube_video_id:
                    logger.info(f"Task {task_id}: Successfully uploaded to YouTube with ID: {youtube_video_id}")
                    # Optionally update task result with youtube id
                    task_result = task_service.get_task(task_id).result or {}
                    task_result['youtube_video_id'] = youtube_video_id
                    task_service.update_task_result(task_id, task_result)
                else:
                    logger.warning(f"Task {task_id}: YouTube upload attempted but failed or returned no ID.")
                    # Decide if this constitutes a partial failure or just a warning

            except Exception as yt_err:
                logger.error(f"Task {task_id}: YouTube upload failed: {yt_err}", exc_info=True)
                # Don't mark the whole task as failed, just log the YouTube error
                # error_message = f"Video generated, but YouTube upload failed: {yt_err}"
                # final_status = TaskStatus.ERROR # Or maybe COMPLETED_WITH_WARNINGS?

    except (ConnectionError, ValueError, IOError, RuntimeError) as e:
        logger.error(f"Task {task_id}: Failed during video generation process: {e}", exc_info=True)
        error_message = f"Task failed: {e}"
        final_status = TaskStatus.ERROR
    except Exception as e:
        logger.exception(f"Task {task_id}: An unexpected error occurred: {e}", exc_info=True)
        error_message = f"An unexpected error occurred: {e}"
        final_status = TaskStatus.ERROR
    finally:
        # 5. Send Callback
        await _send_final_callback(task, final_status, output_video_path, error_message)

        # 6. Cleanup downloaded source files
        files_to_delete = []
        if image_path_temp:
            files_to_delete.append(image_path_temp)
        if audio_path_temp:
            files_to_delete.append(audio_path_temp)

        if files_to_delete:
            logger.info(f"Task {task_id}: Cleaning up source files: {files_to_delete}")
            # Run cleanup in executor as it involves file I/O
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, video_service.cleanup_files, files_to_delete)

        # Note: The generated video file (output_video_path) is NOT deleted here.
        # It will be cleaned up later by the scheduled CleanupService.
        logger.info(f"Background task finished: Generate Video {task_id}. Final Status: {final_status}")


async def run_publish_video_task(task_id: str):
    """Handles the asynchronous video publishing process (primarily YouTube)."""
    task = task_service.get_task(task_id)
    if not task or not isinstance(task.details, dict):
        logger.error(f"Publish task {task_id}: Not found or details missing.")
        return

    details: PublishVideoDetails = PublishVideoDetails(**task.details)

    task_service.set_task_processing(task_id)
    logger.info(f"Starting background task: Publish Video {task_id} from {details.video_url}")

    video_path_temp: Optional[Path] = None
    output_video_path_perm: Optional[Path] = None # Path if moved to static
    error_message: Optional[str] = None
    final_status: TaskStatus = TaskStatus.ERROR
    youtube_video_id: Optional[str] = None

    try:
        # 1. Download the video file specified in the request
        logger.info(f"Task {task_id}: Downloading video from {details.video_url}")
        video_path_temp = await file_downloader_service.download_file(str(details.video_url), task_id)

        # 2. Generate a filename and move to permanent static location
        # We need the video file locally to upload it to YouTube
        # We also make it available via signed URL as per generate-video flow
        output_filename = video_service._generate_video_filename(task_id) # Reuse naming convention
        output_video_path_perm = file_downloader_service.move_to_permanent_location(video_path_temp, output_filename)
        logger.info(f"Task {task_id}: Video downloaded and saved to {output_video_path_perm}")

        # 3. Upload to YouTube
        logger.info(f"Task {task_id}: Attempting YouTube upload.")
        youtube_video_id = await youtube_service.upload_video(output_video_path_perm, details)

        if youtube_video_id:
            logger.info(f"Task {task_id}: Successfully uploaded to YouTube with ID: {youtube_video_id}")
            final_status = TaskStatus.COMPLETED
        else:
            error_message = "YouTube upload failed or returned no ID."
            logger.error(f"Task {task_id}: {error_message}")
            final_status = TaskStatus.ERROR

    except (ConnectionError, ValueError, IOError, RuntimeError) as e:
        logger.error(f"Task {task_id}: Failed during video publishing process: {e}", exc_info=True)
        error_message = f"Task failed: {e}"
        final_status = TaskStatus.ERROR
    except Exception as e:
        logger.exception(f"Task {task_id}: An unexpected error occurred: {e}", exc_info=True)
        error_message = f"An unexpected error occurred: {e}"
        final_status = TaskStatus.ERROR
    finally:
        # 4. Send Callback
        # Include YouTube ID in result if successful
        result_data = {'video_url': str(output_video_path_perm), 'youtube_video_id': youtube_video_id} if final_status == TaskStatus.COMPLETED else {}
        await _send_final_callback(task, final_status, output_video_path_perm, error_message)

        # 5. Cleanup temporary downloaded file (if it wasn't moved)
        if video_path_temp and video_path_temp.exists():
            logger.info(f"Task {task_id}: Cleaning up temporary source file: {video_path_temp}")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, file_downloader_service.cleanup_temp_file, video_path_temp)

        # Note: The final video file (output_video_path_perm) is NOT deleted here.
        # It will be cleaned up later by the scheduled CleanupService.
        logger.info(f"Background task finished: Publish Video {task_id}. Final Status: {final_status}") 