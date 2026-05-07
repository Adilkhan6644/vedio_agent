from __future__ import annotations

import time
from typing import Any

from app.logging_utils import get_logger


logger = get_logger(__name__)


class HygenPollingService:
    def __init__(self, heygen_client: Any, max_poll_seconds: int, poll_interval_seconds: int):
        self.heygen_client = heygen_client
        self.max_poll_seconds = max_poll_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def wait_for_video_url(self, generated_video_id: str, job_id: str) -> str:
        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed > self.max_poll_seconds:
                raise TimeoutError(f"Timed out waiting for HeyGen video {generated_video_id}")

            status_payload = self.heygen_client.get_video_status(generated_video_id)
            status = str(status_payload.get("status", "unknown")).lower()
            video_url = (
                status_payload.get("video_url")
                or status_payload.get("url")
                or status_payload.get("download_url")
            )

            logger.info(
                "Polled HeyGen generation status",
                extra={
                    "job_id": job_id,
                    "generated_video_id": generated_video_id,
                    "stage": "heygen_poll",
                    "status": status,
                },
            )

            if status in {"completed", "success", "done"} and video_url:
                return video_url

            if status in {"failed", "error", "canceled", "cancelled"}:
                raise RuntimeError(f"HeyGen generation failed for {generated_video_id}: {status_payload}")

            time.sleep(self.poll_interval_seconds)
