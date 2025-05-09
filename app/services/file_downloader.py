import httpx
import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse
import logging

from app.models.settings import settings
from app.services.r2_service import r2_service

logger = logging.getLogger(__name__)

class FileDownloaderService:
    def __init__(self, download_dir: str = settings.STATIC_DIR):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        # Create a temporary subdirectory for downloads to avoid cluttering the main static dir
        self.temp_dir = self.download_dir / "_temp_downloads"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def download_file(self, url: str, task_id: str) -> Path:
        """Downloads a file from a URL to a temporary location specific to the task."""
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path) if parsed_url.path else f"{uuid.uuid4()}"
        # Sanitize filename if needed, or use a UUID
        safe_filename = f"{task_id}_{uuid.uuid4().hex}_{filename}" # Ensure uniqueness and link to task

        download_path = self.temp_dir / safe_filename

        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                async with client.stream("GET", url) as response:
                    response.raise_for_status() # Raise an exception for bad status codes
                    with open(download_path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
                return download_path
            except httpx.RequestError as e:
                raise ConnectionError(f"Error downloading {url}: {e}") from e
            except httpx.HTTPStatusError as e:
                raise ValueError(f"Error response {e.response.status_code} while downloading {url}") from e
            except Exception as e:
                # Clean up partial download if any error occurs
                if download_path.exists():
                    os.remove(download_path)
                raise IOError(f"Failed to write downloaded file from {url}: {e}") from e

    async def download_r2_source_file(self, file_key: str, task_id: str) -> Path:
        """Downloads a file from the R2 source bucket to a temporary location specific to the task."""
        # Generate a unique local filename to avoid collisions, including task_id for traceability
        # Extract a base name from the key if possible, or use a UUID
        base_name = file_key.split('/')[-1] if '/' in file_key else file_key
        safe_filename = f"{task_id}_{uuid.uuid4().hex}_{base_name}"
        download_path = self.temp_dir / safe_filename

        try:
            logger.info(f"Attempting to download R2 source file '{file_key}' for task '{task_id}' to '{download_path}'")
            # r2_service.download_file_from_source_bucket is synchronous, needs to be run in executor
            # However, the current structure of r2_service calls boto3 which is blocking.
            # For now, we call it directly. If this becomes a bottleneck, consider executor.
            r2_service.download_file_from_source_bucket(file_key=file_key, destination_path=download_path)
            logger.info(f"Successfully downloaded R2 source file '{file_key}' to '{download_path}'")
            return download_path
        except Exception as e:
            # Ensure cleanup if download fails partway or if file exists from a previous attempt
            if download_path.exists():
                try:
                    os.remove(download_path)
                except OSError as rm_err:
                    logger.error(f"Error cleaning up partially downloaded R2 file {download_path}: {rm_err}")
            # Re-raise the original exception to be handled by the caller
            logger.error(f"Failed to download R2 source file '{file_key}' for task '{task_id}': {e}", exc_info=True)
            raise # Re-raise the caught exception (could be HTTPException from r2_service or other)

    def move_to_permanent_location(self, temp_path: Path, final_filename: str) -> Path:
        """Moves a downloaded file from the temporary location to the main static directory."""
        permanent_path = self.download_dir / final_filename
        shutil.move(str(temp_path), str(permanent_path))
        return permanent_path

    def cleanup_temp_file(self, temp_path: Path):
        """Deletes a file from the temporary download directory."""
        if temp_path.exists() and temp_path.is_file() and temp_path.parent == self.temp_dir:
            os.remove(temp_path)

    def get_static_file_path(self, filename: str) -> Path:
        """Gets the full path for a file in the main static directory."""
        return self.download_dir / filename

# Singleton instance
file_downloader_service = FileDownloaderService() 