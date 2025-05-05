import os
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.models.settings import settings

logger = logging.getLogger(__name__)

class CleanupService:
    def __init__(self, static_dir: str = settings.STATIC_DIR, max_age_hours: int = settings.MAX_VIDEO_AGE_HOURS):
        self.static_dir = Path(static_dir)
        self.max_age_seconds = max_age_hours * 3600
        self.scheduler = AsyncIOScheduler()

    async def cleanup_old_files(self):
        """Scans the static directory and deletes files older than the max age."""
        logger.info(f"Running cleanup task. Deleting files older than {self.max_age_seconds / 3600} hours in {self.static_dir}")
        now = time.time()
        deleted_count = 0
        error_count = 0

        if not self.static_dir.exists():
            logger.warning(f"Cleanup task: Static directory {self.static_dir} not found.")
            return

        for filepath in self.static_dir.glob('video_*.mp4'): # Target only generated video files
            try:
                if filepath.is_file():
                    file_age = now - filepath.stat().st_mtime
                    if file_age > self.max_age_seconds:
                        os.remove(filepath)
                        deleted_count += 1
                        logger.info(f"Deleted old file: {filepath} (age: {file_age:.0f}s)")
            except OSError as e:
                error_count += 1
                logger.error(f"Error deleting file {filepath}: {e}")
            except Exception as e:
                error_count += 1
                logger.error(f"Unexpected error processing file {filepath} for cleanup: {e}", exc_info=True)

        # Also clean up old temporary download files if any linger
        temp_dir = self.static_dir / "_temp_downloads"
        if temp_dir.exists():
             for filepath in temp_dir.iterdir():
                 try:
                     if filepath.is_file():
                         file_age = now - filepath.stat().st_mtime
                         # Use a shorter lifespan for temp files, e.g., max_age or maybe less
                         if file_age > self.max_age_seconds: # Or a shorter duration
                             os.remove(filepath)
                             deleted_count += 1
                             logger.info(f"Deleted old temporary file: {filepath} (age: {file_age:.0f}s)")
                 except OSError as e:
                     error_count += 1
                     logger.error(f"Error deleting temporary file {filepath}: {e}")
                 except Exception as e:
                     error_count += 1
                     logger.error(f"Unexpected error processing temporary file {filepath} for cleanup: {e}", exc_info=True)


        logger.info(f"Cleanup task finished. Deleted: {deleted_count} files. Errors: {error_count}")

    def start(self):
        """Starts the scheduled cleanup task."""
        if not self.scheduler.running:
            self.scheduler.add_job(
                self.cleanup_old_files,
                trigger=IntervalTrigger(hours=settings.CLEANUP_INTERVAL_HOURS),
                id="cleanup_old_files_job",
                replace_existing=True,
                misfire_grace_time=300 # Allow 5 minutes delay if scheduler was busy
            )
            self.scheduler.start()
            logger.info(f"Cleanup scheduler started. Runs every {settings.CLEANUP_INTERVAL_HOURS} hour(s).")

    def stop(self):
        """Stops the scheduled cleanup task."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Cleanup scheduler stopped.")

# Singleton instance
cleanup_service = CleanupService() 