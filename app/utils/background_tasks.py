import logging
import asyncio
from pathlib import Path
from typing import Optional
import os
import uuid
from pydantic import HttpUrl

from app.models.api_models import TaskMetadata, TaskStatus, GenerateVideoDetails, UploadYoutubeVideoDetails, GenerateVideoCallbackPayload
from app.services.task_service import task_service
from app.services.video_service import video_service
from app.services.file_downloader import file_downloader_service
from app.services.callback_service import callback_service
from app.services.r2_service import r2_service
from app.services.youtube_service import youtube_service
from app.models.settings import settings

logger = logging.getLogger(__name__)

async def _send_final_callback(task: TaskMetadata, status: TaskStatus, r2_object_key: Optional[str] = None, error_message: Optional[str] = None):
    """Helper function to construct and send the final callback, using R2 presigned URL if applicable."""
    # The final_video_url_for_callback variable is no longer needed as we directly use r2_object_key.
    # final_video_url_for_callback: Optional[str] = None

    # The original logic for generating presigned URL is removed.

    callback_payload = GenerateVideoCallbackPayload(
        taskId=task.id,
        status=status.value, # Use 'completed' or 'error' string
        video_bucket_key=r2_object_key, # Pass the R2 object key directly
        error=error_message
    )

    # Update task one last time before sending callback
    if status == TaskStatus.COMPLETED and r2_object_key:
        # Remove 'signed_r2_url' from the result
        task_service.set_task_completed(task.id, result={'r2_object_key': r2_object_key})
    else:
        task_service.set_task_error(task.id, error_message or "Unknown error")

    # Send the callback
    await callback_service.send_callback(str(task.details['callback_url']), callback_payload)


async def run_generate_video_task(task_id: str):
    """Handles the asynchronous video generation process using R2 for inputs and outputs."""
    task = task_service.get_task(task_id)
    if not task or not isinstance(task.details, dict): # Check details is dict
        logger.error(f"Generate task {task_id}: Not found or details missing.")
        return

    details: GenerateVideoDetails = GenerateVideoDetails(**task.details)

    task_service.set_task_processing(task_id)
    logger.info(f"Starting background task: Generate Video {task_id} from R2 keys: image='{details.background_image_key}', audio='{details.audio_file_key}'")

    image_path_temp: Optional[Path] = None
    audio_path_temp: Optional[Path] = None
    output_video_path_local: Optional[Path] = None
    r2_video_object_key: Optional[str] = None
    error_message: Optional[str] = None
    final_status: TaskStatus = TaskStatus.ERROR # Assume error until success
    loop = asyncio.get_running_loop()

    try:
        # 1. Download files from R2 Source Bucket
        logger.info(f"Task {task_id}: Downloading background image R2 key {details.background_image_key}")
        image_path_temp = await file_downloader_service.download_r2_source_file(details.background_image_key, task_id)
        
        logger.info(f"Task {task_id}: Downloading audio file R2 key {details.audio_file_key}")
        audio_path_temp = await file_downloader_service.download_r2_source_file(details.audio_file_key, task_id)

        # 2. Determine Output Filename/R2 Object Key from task details
        # The output_bucket_key from the payload will be used as the R2 object key
        # and also as the base for the local temporary filename.
        if not details.output_bucket_key:
            logger.error(f"Task {task_id}: output_bucket_key is missing from task details.")
            raise ValueError("output_bucket_key is required but was not provided.")
        output_filename = details.output_bucket_key # This is now the R2 object key

        # 3. Generate Video locally (CPU-bound)
        logger.info(f"Task {task_id}: Starting local video creation with MoviePy. Output filename: {output_filename}")
        output_video_path_local = await loop.run_in_executor(
            None, # Use default executor (ThreadPoolExecutor)
            video_service.create_video_from_image_audio,
            image_path_temp,
            audio_path_temp,
            Path(output_filename).name # Pass only the filename part for local temp storage, video_service prepends static_dir
        )
        logger.info(f"Task {task_id}: Local video created successfully at {output_video_path_local}")

        # 4. Upload generated video to R2 Output Bucket
        logger.info(f"Task {task_id}: Uploading {output_video_path_local} to R2 as {output_filename}")
        r2_video_object_key = await loop.run_in_executor(
            None,
            r2_service.upload_file_to_output_bucket,
            output_video_path_local, 
            output_filename # Using the generated filename as the R2 object key
        )
        logger.info(f"Task {task_id}: Successfully uploaded video to R2 with key: {r2_video_object_key}")
        final_status = TaskStatus.COMPLETED

    except (ConnectionError, ValueError, IOError, RuntimeError) as e:
        logger.error(f"Task {task_id}: Failed during video generation process: {e}", exc_info=True)
        error_message = f"Task failed: {e}"
        final_status = TaskStatus.ERROR
    except Exception as e:
        logger.exception(f"Task {task_id}: An unexpected error occurred: {e}", exc_info=True)
        error_message = f"An unexpected error occurred: {e}"
        final_status = TaskStatus.ERROR
    finally:
        # 6. Send Callback (with R2 object key if successful)
        await _send_final_callback(task, final_status, r2_video_object_key, error_message)

        # 7. Cleanup downloaded temporary source files
        files_to_delete_temp = []
        if image_path_temp: files_to_delete_temp.append(image_path_temp)
        if audio_path_temp: files_to_delete_temp.append(audio_path_temp)

        if files_to_delete_temp:
            logger.info(f"Task {task_id}: Cleaning up temporary source files: {files_to_delete_temp}")
            await loop.run_in_executor(None, file_downloader_service.cleanup_temp_file, files_to_delete_temp[0]) # cleanup_temp_file needs individual calls
            if len(files_to_delete_temp) > 1:
                 await loop.run_in_executor(None, file_downloader_service.cleanup_temp_file, files_to_delete_temp[1])


        # 8. Cleanup locally generated video file (as it's now in R2)
        if output_video_path_local and output_video_path_local.exists():
            logger.info(f"Task {task_id}: Cleaning up locally generated video file: {output_video_path_local}")
            try:
                await loop.run_in_executor(None, os.remove, output_video_path_local)
            except Exception as e_clean:
                logger.error(f"Task {task_id}: Failed to clean up local video file {output_video_path_local}: {e_clean}")
        
        logger.info(f"Background task finished: Generate Video {task_id}. Final Status: {final_status}. R2 Key: {r2_video_object_key}")

async def run_upload_youtube_video_task(task_id: str):
    """Handles the asynchronous video publishing process (primarily YouTube). Video source can be a URL or an R2 key."""
    task = task_service.get_task(task_id)
    if not task or not isinstance(task.details, dict):
        logger.error(f"Publish task {task_id}: Not found or details missing.")
        return

    details: UploadYoutubeVideoDetails = UploadYoutubeVideoDetails(**task.details)

    task_service.set_task_processing(task_id)
    logger.info(f"Starting background task: Publish Video {task_id} from source: {details.video_url}")

    video_path_temp: Optional[Path] = None       # Temp path for downloaded video if source is URL
    r2_output_object_key: Optional[str] = None # R2 key if original video is from R2 or if uploaded to our R2 as part of this task
    local_video_path_for_upload: Optional[Path] = None # The definitive local path of the video to be uploaded to YT
    error_message: Optional[str] = None
    final_status: TaskStatus = TaskStatus.ERROR
    youtube_video_id_from_service: Optional[str] = None # To store result from youtube_service
    youtube_video_url_from_service: Optional[HttpUrl] = None # To store result from youtube_service
    # comment_id_from_service: Optional[str] = None # If needed from result

    try:
        # This task is now primarily a wrapper for youtube_video_service.process_upload_task
        # The youtube_video_service.process_upload_task handles its own status updates and callbacks.
        # We just need to call it and await its completion.
        
        # Ensure task details are correctly parsed if needed here, though process_upload_task does it too.
        # upload_details = YouTubeVideoUploadRequest(**task.details) # Already done in process_upload_task

        # The actual processing and callback sending is delegated to YouTubeVideoService.
        await youtube_video_service.process_upload_task(task_id) 
        
        # After youtube_video_service.process_upload_task completes, the task status in the database
        # will be updated by it (COMPLETED or ERROR), and the callback will have been sent by it.
        # We can retrieve the final status and result if needed for logging here, but no separate callback.
        updated_task = task_service.get_task(task_id) # Get the latest task status
        if updated_task:
            final_status = updated_task.status
            if updated_task.result:
                youtube_video_id_from_service = updated_task.result.get('youtube_video_id')
                youtube_video_url_str = updated_task.result.get('youtube_video_url')
                if youtube_video_url_str: # Convert string back to HttpUrl if needed for local use
                    try:
                        youtube_video_url_from_service = HttpUrl(youtube_video_url_str)
                    except Exception:
                        logger.warning(f"Task {task_id}: Could not parse youtube_video_url from result: {youtube_video_url_str}")
            logger.info(f"Task {task_id}: YouTube processing via service completed. Final status: {final_status}")
        else:
            logger.error(f"Task {task_id}: Task object not found after YouTube service processing.")
            final_status = TaskStatus.ERROR # Fallback status

    except Exception as e:
        # This top-level exception catch is a fallback.
        # Most errors should be caught within youtube_video_service.process_upload_task,
        # which then sets task status and sends an error callback.
        error_message = f"Critical error in run_upload_youtube_video_task for {task_id}: {e}"
        logger.exception(error_message, exc_info=True)
        task_service.set_task_error(task_id, error_message) # Ensure task is marked as error
        final_status = TaskStatus.ERROR
        # Potentially send a generic callback here if process_upload_task failed catastrophically before sending its own.
        # However, youtube_video_service.process_upload_task has its own robust try/except/finally for callbacks.
        # So, an additional callback here might be redundant or cause double callbacks.
        # For now, we rely on youtube_video_service to send its callback.

    finally:
        # The callback is now handled by youtube_video_service.process_upload_task.
        # No need to call _send_final_callback here for YouTube upload tasks.
        # logger.info(f"Background task finished: Upload YouTube Video {task_id}. Final Status: {final_status}. YouTube ID: {youtube_video_id_from_service}")

        # Cleanup of local files (e.g., video_path_temp, if it were managed here) is also handled by youtube_video_service.process_upload_task
        # The existing run_generate_video_task shows cleanup logic; similar isolated cleanup might be needed if this task did downloads directly.
        # But since process_upload_task handles downloads and their cleanup, no direct action here.
        pass # No specific cleanup or callback sending action in this finally block for this task type.

# Register tasks with a dictionary for dynamic calling if desired, or call directly.
# background_task_runners = {
# ... existing code ...

# ... rest of the file remains unchanged ... 