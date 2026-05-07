from __future__ import annotations

from pathlib import Path

from app.logging_utils import get_logger


logger = get_logger(__name__)


class CleanupService:
    def cleanup_files(self, files: list[Path], job_id: str) -> None:
        for file_path in files:
            try:
                if file_path.exists():
                    file_path.unlink()
                    logger.info("Deleted temp file", extra={"job_id": job_id, "stage": "cleanup", "file": str(file_path)})
            except Exception:
                logger.warning(
                    "Failed to delete temp file",
                    extra={"job_id": job_id, "stage": "cleanup", "file": str(file_path)},
                    exc_info=True,
                )
