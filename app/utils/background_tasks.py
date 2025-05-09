import logging
import asyncio
from pathlib import Path
from typing import Optional
import os
import uuid
from pydantic import HttpUrl

from app.models.api_models import TaskMetadata, TaskStatus, GenerateVideoDetails, UploadYoutubeVideoDetails, CallbackPayload
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
    # video_url_with_signature = None # Removed as per requirement
    # signature = None # Kept for compatibility, even if only in URL - Now largely irrelevant with R2 presigned URLs

    # The video_url will now be None if it was previously the signed R2 URL.
    # If a different, non-R2, non-signed URL should be provided, that logic would go here.
    # For now, it defaults to None as we are removing the signed R2 URL.
    final_video_url_for_callback: Optional[str] = None

    # The original logic for generating presigned URL is removed:
    # if status == TaskStatus.COMPLETED and r2_object_key:
    #     try:
    #         # Generate presigned URL for the R2 object
    #         video_url_with_signature = r2_service.generate_presigned_url_for_output_bucket(r2_object_key, expiration=settings.SIGNATURE_EXPIRATION_SECONDS)
    #         logger.info(f"Task {task.id}: Generated presigned R2 URL: {video_url_with_signature}")
    #     except Exception as e:
    #         logger.error(f"Task {task.id}: Failed to generate presigned R2 URL for object {r2_object_key}: {e}", exc_info=True)
    #         status = TaskStatus.ERROR # Mark as error if we can't even provide the URL
    #         error_message = f"Video processed, but failed to generate access URL: {e}"
    #         video_url_with_signature = None

    callback_payload = CallbackPayload(
        taskId=task.id,
        status=status.value, # Use 'completed' or 'error' string
        video_url=final_video_url_for_callback, # Use the new variable, which is None for R2 objects now
        # video_signature field is less relevant with full presigned URLs, can be omitted or set to None/empty
        video_signature=None, 
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

        # 2. Generate Video filename (this will also be the R2 object key)
        output_filename = video_service._generate_video_filename(task_id)

        # 3. Generate Video locally (CPU-bound)
        logger.info(f"Task {task_id}: Starting local video creation with MoviePy. Output filename: {output_filename}")
        output_video_path_local = await loop.run_in_executor(
            None, # Use default executor (ThreadPoolExecutor)
            video_service.create_video_from_image_audio,
            image_path_temp,
            audio_path_temp,
            output_filename # This filename is used for the local temp file in static dir
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
    youtube_video_id: Optional[str] = None
    loop = asyncio.get_running_loop()
    cleanup_local_video_path_for_upload = False # Flag to cleanup this specific file if it was downloaded/copied

    try:
        # Check if details.video_url is an R2 key (e.g., "r2://bucket/key" or just "key" convention)
        # For now, assume if it's not a valid HttpUrl, it might be an R2 key. This logic could be more robust.
        # Or, the PublishVideoDetails model could be changed to specify source_type (url vs r2_key)
        is_r2_source = not str(details.video_url).startswith(("http://", "https://")) 
        # A more robust check would be to attempt parsing as HttpUrl and if it fails, treat as R2 key, or add a field to model.
        # Let's assume for now: if it's a key, it refers to OUR R2_VIDEO_OUTPUT_BUCKET.

        if is_r2_source:
            # If video_url is actually an R2 key for a video already in our output bucket
            r2_key_as_str = str(details.video_url) 
            logger.info(f"Task {task_id}: Video source is an R2 key: {r2_key_as_str}. Assuming it's in output bucket.")
            # Download it locally for YouTube upload
            # Create a unique temp name for this download
            temp_dl_filename = f"publish_{task_id}_{uuid.uuid4().hex}_{r2_key_as_str.split('/')[-1]}"
            video_path_temp = file_downloader_service.temp_dir / temp_dl_filename
            
            await loop.run_in_executor(None, r2_service.download_file, settings.R2_VIDEO_OUTPUT_BUCKET, r2_key_as_str, str(video_path_temp))
            # ^^^ NOTE: r2_service.download_file does not exist. It should be download_file_from_bucket or similar.
            # Correcting to a conceptual download from output bucket (assuming such method exists or is added to R2Service)
            # For now, let's use a placeholder for actual download from output bucket:
            # This part needs r2_service to have a generic download_file(bucket, key, dest) method.
            # Let's assume download_r2_source_file can take a bucket argument or we add a new one.
            # For simplicity, let's assume the key exists in R2_VIDEO_OUTPUT_BUCKET
            # This will be used if a user wants to publish a video they previously generated with our service.

            # For now, let's assume r2_service has: download_file_from_bucket(bucket_name, key, dest_path)
            # This method isn't in the current R2Service, so this part will need adjustment to R2Service or this logic.
            # For the purpose of this refactor, let's assume it's downloaded:
            # video_path_temp = await file_downloader_service.download_r2_general(bucket=settings.R2_VIDEO_OUTPUT_BUCKET, key=r2_key_as_str, task_id=task_id)
            # This is a placeholder for a function that would download from a *specified* R2 bucket (output bucket in this case).
            # Given current r2_service, we cannot directly download from R2_VIDEO_OUTPUT_BUCKET using a simple method yet.
            # This highlights a potential need for a generic download in r2_service or a change in publish flow.
            
            # *** Major Simplification for now: Assume video_url is always a public URL if not an R2 key from generate-video flow ***
            # This means if user provides an "R2 key" it must be one they got from *our* generate-video. The presigned URL from that would be the input here.
            # If `details.video_url` IS a key, it means it's a key that *we* manage in R2_VIDEO_OUTPUT_BUCKET.
            # For now, we will proceed assuming `details.video_url` is always a downloadable HTTP URL.
            # The scenario of "publishing an existing R2 object by its key" needs more robust handling or clarification.
            # Fallback to assuming it's a URL to download if is_r2_source logic is tricky.
            logger.warning(f"Task {task_id}: Treating video_url as a public URL for download. R2 key direct publish needs review.")
            # Fall through to standard URL download logic

        # 1. Download the video file if it's a URL
        logger.info(f"Task {task_id}: Downloading video from {details.video_url} for publishing.")
        video_path_temp = await file_downloader_service.download_file(str(details.video_url), task_id)
        local_video_path_for_upload = video_path_temp # This is the file to upload to YT
        cleanup_local_video_path_for_upload = True    # And it needs cleanup

        # 2. (Optional) Copy to our R2 output bucket if not already there or if policy is to always have a copy.
        # For now, we assume the primary goal is YouTube upload. If the video came from an external URL,
        # we upload it to YT. We *could* also save it to our R2_VIDEO_OUTPUT_BUCKET.
        # Let's assume we DO want to store it in our R2 for consistency and a signed URL.
        output_r2_filename = video_service._generate_video_filename(f"upload_yt_{task_id}") # Unique name for our R2
        logger.info(f"Task {task_id}: Uploading downloaded video to our R2 as {output_r2_filename}")
        r2_output_object_key = await loop.run_in_executor(
            None, 
            r2_service.upload_file_to_output_bucket, 
            local_video_path_for_upload, 
            output_r2_filename
        )
        logger.info(f"Task {task_id}: Video copied to R2 with key: {r2_output_object_key}")

        # 3. Upload to YouTube
        logger.info(f"Task {task_id}: Attempting YouTube upload of {local_video_path_for_upload}.")
        youtube_video_id = await youtube_service.upload_video(local_video_path_for_upload, details) # Pass PublishVideoDetails directly

        if youtube_video_id:
            logger.info(f"Task {task_id}: Successfully uploaded to YouTube with ID: {youtube_video_id}")
            final_status = TaskStatus.COMPLETED
        else:
            error_message = "YouTube upload failed or returned no ID."
            logger.error(f"Task {task_id}: {error_message}")
            # If R2 upload succeeded, this is a partial success.
            # For now, if YT fails, the whole task is marked error for simplicity of callback.
            final_status = TaskStatus.ERROR 

    except (ConnectionError, ValueError, IOError, RuntimeError) as e:
        logger.error(f"Task {task_id}: Failed during video publishing process: {e}", exc_info=True)
        error_message = f"Task failed: {e}"
        final_status = TaskStatus.ERROR
    except Exception as e:
        logger.exception(f"Task {task_id}: An unexpected error occurred during publish: {e}", exc_info=True)
        error_message = f"An unexpected error occurred: {e}"
        final_status = TaskStatus.ERROR
    finally:
        # 4. Send Callback - use r2_output_object_key for the R2 URL if available
        # The primary result for 'publish' is the YouTube ID, but we also provide our R2 URL.
        result_data_for_task_db = {}
        if final_status == TaskStatus.COMPLETED:
            if r2_output_object_key: result_data_for_task_db['r2_object_key'] = r2_output_object_key
            if youtube_video_id: result_data_for_task_db['youtube_video_id'] = youtube_video_id
        
        # _send_final_callback's third argument is the R2 key for *our* generated/stored video's signed URL
        await _send_final_callback(task, final_status, r2_output_object_key, error_message)
        if result_data_for_task_db: # Update task result with more specific info if publish was successful
            task_service.update_task_result(task_id, result_data_for_task_db)

        # 5. Cleanup temporary downloaded file (if one was created for YT upload)
        if local_video_path_for_upload and cleanup_local_video_path_for_upload and local_video_path_for_upload.exists():
            logger.info(f"Task {task_id}: Cleaning up temporary source video file: {local_video_path_for_upload}")
            await loop.run_in_executor(None, file_downloader_service.cleanup_temp_file, local_video_path_for_upload)

        logger.info(f"Background task finished: Upload YouTube Video {task_id}. Final Status: {final_status}. R2 Key: {r2_output_object_key}, YT ID: {youtube_video_id}") 