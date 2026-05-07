from __future__ import annotations

import random
import socket
import time
from pathlib import Path
from typing import Any

import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.logging_utils import get_logger


logger = get_logger(__name__)


RETRIABLE_STATUS_CODES = {500, 502, 503, 504}
RETRIABLE_EXCEPTIONS = (
    httplib2.HttpLib2Error,
    IOError,
    ConnectionError,
    TimeoutError,
    socket.timeout,
)


class YouTubeUploadService:
    def __init__(self, credentials: Any, chunk_size_mb: int = 8, max_retries: int = 8):
        self.credentials = credentials
        self.chunk_size_bytes = max(chunk_size_mb, 1) * 1024 * 1024
        self.max_retries = max_retries

    def upload_short(
        self,
        *,
        file_path: Path,
        title: str,
        description: str,
        tags: list[str] | None,
        category_id: str,
        privacy_status: str,
        job_id: str,
    ) -> dict[str, Any]:
        youtube = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)

        if "#shorts" not in description.lower() and "#shorts" not in title.lower():
            description = f"{description}\n\n#shorts".strip()

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            str(file_path),
            chunksize=self.chunk_size_bytes,
            resumable=True,
            mimetype="video/mp4",
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response, retry_count = self._resumable_upload(request, job_id)
        video_id = response["id"]

        logger.info(
            "YouTube upload completed",
            extra={"job_id": job_id, "stage": "youtube_upload", "youtube_video_id": video_id},
        )

        return {
            "youtube_video_id": video_id,
            "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
            "retry_count": retry_count,
            "raw_response": response,
        }

    def _resumable_upload(self, request, job_id: str) -> tuple[dict[str, Any], int]:
        response = None
        retry = 0

        while response is None:
            try:
                status, response = request.next_chunk()

                if status:
                    logger.info(
                        "YouTube upload progress",
                        extra={
                            "job_id": job_id,
                            "stage": "youtube_upload",
                            "progress_percent": round(status.progress() * 100, 2),
                        },
                    )

                if response and "id" not in response:
                    raise RuntimeError(f"Unexpected upload response: {response}")

            except HttpError as exc:
                if exc.resp.status in RETRIABLE_STATUS_CODES or self._is_rate_limit_error(exc):
                    retry = self._next_retry_or_raise(retry, exc)
                    sleep_seconds = self._backoff(retry)
                    logger.warning(
                        "Retriable YouTube HTTP error",
                        extra={"job_id": job_id, "stage": "youtube_upload", "retry": retry},
                        exc_info=True,
                    )
                    time.sleep(sleep_seconds)
                else:
                    raise
            except RETRIABLE_EXCEPTIONS as exc:
                retry = self._next_retry_or_raise(retry, exc)
                sleep_seconds = self._backoff(retry)
                logger.warning(
                    "Retriable upload connection error",
                    extra={"job_id": job_id, "stage": "youtube_upload", "retry": retry},
                    exc_info=True,
                )
                time.sleep(sleep_seconds)

        return response, retry

    def _next_retry_or_raise(self, retry: int, exc: Exception) -> int:
        retry += 1
        if retry > self.max_retries:
            raise RuntimeError(f"YouTube resumable upload exhausted retries: {exc}") from exc
        return retry

    @staticmethod
    def _backoff(retry: int) -> float:
        return min((2 ** retry) + random.random(), 60.0)

    @staticmethod
    def _is_rate_limit_error(exc: HttpError) -> bool:
        if exc.resp.status not in {403, 429}:
            return False

        content = ""
        if getattr(exc, "content", None):
            try:
                content = exc.content.decode("utf-8", errors="ignore")
            except Exception:
                content = str(exc.content)

        lowered = content.lower()
        return any(
            marker in lowered
            for marker in [
                "ratelimitexceeded",
                "userratelimitexceeded",
                "quotaexceeded",
                "dailylimitexceeded",
            ]
        )
