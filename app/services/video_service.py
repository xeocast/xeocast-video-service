import os
import uuid
from pathlib import Path
import logging

# Import moviepy components
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips

from app.models.settings import settings
from app.services.file_downloader import file_downloader_service

logger = logging.getLogger(__name__)

class VideoService:

    def _generate_video_filename(self, task_id: str) -> str:
        """Generates a unique filename for the output video."""
        return f"video_{task_id}_{uuid.uuid4().hex}.mp4"

    def create_video_from_image_audio(
        self,
        image_path: Path,
        audio_path: Path,
        output_filename: str
    ) -> Path:
        """Generates a video file from an image and an audio file using MoviePy."""
        output_path = file_downloader_service.get_static_file_path(output_filename)

        logger.info(f"Starting video generation: image={image_path}, audio={audio_path}, output={output_path}")

        try:
            # --- MoviePy Logic Start (Adapted from visualizer.py) ---
            audio_clip = AudioFileClip(str(audio_path))
            image_clip = ImageClip(str(image_path))

            # Set the duration of the image clip to match the audio duration
            image_clip = image_clip.with_duration(audio_clip.duration)

            # Set the audio of the image clip
            video_clip = image_clip.with_audio(audio_clip)

            # Set fps, otherwise it defaults to a low value that might cause issues
            # Choose a standard frame rate like 24, 25 or 30
            fps = 24

            # Write the result to a file
            # Use specified codec, bitrate, and threads for potentially better performance/compatibility
            # preset='ultrafast' can speed up encoding but might reduce quality
            video_clip.write_videofile(
                str(output_path),
                codec='libx264',      # Common video codec
                audio_codec='aac',    # Common audio codec
                fps=fps,
                # preset='ultrafast',
                # threads=4,          # Adjust based on server cores
                # bitrate="5000k"     # Adjust as needed for quality vs size
                logger=None # Can set to 'bar' for progress bar if running interactively
            )

            # Close clips to release file handles
            audio_clip.close()
            image_clip.close()
            video_clip.close()
            # --- MoviePy Logic End ---

            logger.info(f"Video generation successful: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error during video generation for {output_filename}: {e}", exc_info=True)
            # Clean up potentially partially created output file
            if output_path.exists():
                try:
                    os.remove(output_path)
                except OSError as rm_err:
                    logger.error(f"Error cleaning up failed video file {output_path}: {rm_err}")
            raise RuntimeError(f"MoviePy failed to generate video: {e}") from e

    def cleanup_files(self, file_paths: list[Path]):
        """Deletes the specified files."""
        for file_path in file_paths:
            if file_path and file_path.exists() and file_path.is_file():
                try:
                    os.remove(file_path)
                    logger.info(f"Cleaned up file: {file_path}")
                except OSError as e:
                    logger.error(f"Error deleting file {file_path}: {e}")

# Singleton instance
video_service = VideoService() 