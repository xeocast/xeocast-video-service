import os
import uuid
from pathlib import Path
import logging

# Import moviepy components
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips, VideoClip, CompositeVideoClip
import librosa
import numpy as np
import cv2

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
            # Load audio with librosa for visualizer
            y, sr = librosa.load(str(audio_path))
            audio_duration = librosa.get_duration(y=y, sr=sr)

            # Compute the mel spectrogram
            melspec = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=20) # Using 20 mel bands as in visualizer.py
            max_val = np.max(melspec) if np.max(melspec) > 0 else 1.0 # Avoid division by zero
            hop_length = 512  # Default hop length in librosa

            # Load background image with OpenCV to get dimensions, then use MoviePy ImageClip
            bg_img_cv = cv2.imread(str(image_path))
            if bg_img_cv is None:
                raise RuntimeError(f"Could not load image file for visualizer: {image_path}")
            bg_img_cv = cv2.cvtColor(bg_img_cv, cv2.COLOR_BGR2RGB) # Convert BGR to RGB
            bg_height, bg_width = bg_img_cv.shape[:2]

            # Define visualizer parameters (similar to visualizer.py)
            num_bars = 20
            max_bar_height_factor = 0.6 # Factor of bg_height
            max_bar_height = int(bg_height * max_bar_height_factor)
            margin = 50
            space = 10
            bar_width = (bg_width - 2 * margin - (num_bars - 1) * space) // num_bars
            if bar_width <= 0: # Ensure bar_width is positive
                bar_width = 10 # Fallback bar_width if calculated is too small or negative


            def make_frame(t):
                # Map video time to spectrogram time index
                i = min(int(round(t * sr / hop_length)), melspec.shape[1] - 1)
                spec_t = melspec[:, i]

                # Compute bar heights
                bar_heights = (spec_t / max_val) * max_bar_height
                bar_heights = bar_heights.astype(int)

                # Create a blank image with alpha channel (transparent) for the visualizer layer
                viz_frame = np.zeros((bg_height, bg_width, 4), dtype=np.uint8)

                for j in range(num_bars):
                    x_left = margin + j * (bar_width + space)
                    x_right = x_left + bar_width
                    # Bars from bottom, growing upwards
                    y_bottom = bg_height - 10 # Small offset from very bottom
                    y_top = max(int(y_bottom - bar_heights[j]), 0)


                    # Ensure integer coordinates and within bounds
                    x_left, x_right = int(x_left), int(x_right)
                    y_top, y_bottom = int(y_top), int(y_bottom)
                    
                    if x_right > x_left and y_bottom > y_top : #Ensure valid rectangle
                         # Draw the bar (white, semi-transparent)
                        cv2.rectangle(viz_frame, (x_left, y_top), (x_right, y_bottom), (255, 255, 255, 180), -1)


                return viz_frame # Return frame with alpha

            # Create background and audio clips
            background_clip = ImageClip(str(image_path)).with_duration(audio_duration)
            audio_clip_main = AudioFileClip(str(audio_path))

            # Create the visualizer clip
            visualizer_clip = VideoClip(make_frame, duration=audio_duration)


            # Composite the background and visualizer
            # The visualizer is placed on top of the background
            final_clip = CompositeVideoClip([background_clip, visualizer_clip.with_position(("center", "center"))], size=(bg_width, bg_height))
            final_clip = final_clip.with_audio(audio_clip_main)


            fps = 24
            final_clip.write_videofile(
                str(output_path),
                codec='libx264',
                audio_codec='aac',
                fps=fps,
                logger=None
            )

            # Close clips
            audio_clip_main.close()
            background_clip.close()
            visualizer_clip.close()
            final_clip.close()
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