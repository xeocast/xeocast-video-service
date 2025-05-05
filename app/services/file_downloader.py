import httpx
import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse

from app.models.settings import settings

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