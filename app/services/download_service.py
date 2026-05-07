from __future__ import annotations

import shutil
import time
import json
import subprocess
from pathlib import Path

import httpx

from app.logging_utils import get_logger


logger = get_logger(__name__)


class VideoDownloadService:
    def __init__(self, max_retries: int = 4, ffprobe_path: str = "ffprobe"):
        self.max_retries = max_retries
        self.ffprobe_path = ffprobe_path

    def download(self, url: str, destination: Path, job_id: str) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "Downloading generated video",
                    extra={"job_id": job_id, "stage": "download", "retry": attempt},
                )
                with httpx.stream("GET", url, timeout=120.0, follow_redirects=True) as response:
                    response.raise_for_status()
                    with open(destination, "wb") as file_obj:
                        for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                            if chunk:
                                file_obj.write(chunk)

                self._validate_file(destination)
                self._validate_duration(destination)
                return destination
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Download attempt failed",
                    extra={"job_id": job_id, "stage": "download", "retry": attempt},
                    exc_info=True,
                )
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 20))

        raise RuntimeError(f"Failed to download video after retries: {last_error}")

    def copy_local_file(self, source_file: Path, destination: Path, job_id: str) -> Path:
        if not source_file.exists():
            raise FileNotFoundError(f"Source file does not exist: {source_file}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Copying source file", extra={"job_id": job_id, "stage": "download"})
        shutil.copy2(source_file, destination)
        self._validate_file(destination)
        self._validate_duration(destination)
        return destination

    @staticmethod
    def _validate_file(path: Path) -> None:
        if not path.exists():
            raise RuntimeError(f"Downloaded file missing: {path}")

        size = path.stat().st_size
        if size <= 0:
            raise RuntimeError(f"Downloaded file is empty: {path}")

    def _validate_duration(self, path: Path) -> None:
        cmd = [
            self.ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed for {path}: {result.stderr.strip()}")

        payload = json.loads(result.stdout or "{}")
        duration = float(payload.get("format", {}).get("duration", 0) or 0)
        if duration <= 0:
            raise RuntimeError(f"Invalid source video duration for {path}")
