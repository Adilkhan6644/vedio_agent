from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.logging_utils import get_logger
from app.services.cleanup_service import CleanupService
from app.services.download_service import VideoDownloadService
from app.services.ffmpeg_service import FfmpegService
from app.services.hygen_service import HygenPollingService
from app.services.metadata_store import UploadMetadataStore
from app.services.oauth_service import OAuthService
from app.services.youtube_service import YouTubeUploadService


logger = get_logger(__name__)


@dataclass
class UploadJobRequest:
    generated_video_id: str | None
    source_url: str | None
    source_file_path: str | None
    title: str
    description: str
    tags: list[str]
    category_id: str
    privacy_status: str
    heygen_api_key: str | None


class ShortsPipelineWorker:
    def __init__(self):
        self.settings = get_settings()
        self.store = UploadMetadataStore(self.settings.upload_db_path)
        self.download_service = VideoDownloadService(
            self.settings.max_download_retries,
            self.settings.ffprobe_path,
        )
        self.ffmpeg_service = FfmpegService(
            ffmpeg_path=self.settings.ffmpeg_path,
            ffprobe_path=self.settings.ffprobe_path,
        )
        self.oauth_service = OAuthService(
            client_secret_file=self.settings.youtube_client_secret_file,
            token_file=self.settings.youtube_token_file,
        )
        self.cleanup_service = CleanupService()

    def create_job(self, request: UploadJobRequest) -> str:
        job_id = str(uuid.uuid4())
        metadata = {
            "title": request.title,
            "description": request.description,
            "tags": request.tags,
            "category_id": request.category_id,
            "privacy_status": request.privacy_status,
        }
        self.store.create_job(
            job_id=job_id,
            generated_video_id=request.generated_video_id,
            source_url=request.source_url,
            source_file=request.source_file_path,
            metadata=metadata,
        )
        return job_id

    async def process_job(self, job_id: str, request: UploadJobRequest) -> None:
        self.store.update_status(job_id, "processing")
        temp_original = self.settings.temp_dir / f"{job_id}_source.mp4"
        temp_shorts = self.settings.temp_dir / f"{job_id}_shorts.mp4"

        try:
            source_url = request.source_url
            if request.generated_video_id and not source_url:
                source_url = await self._poll_heygen_for_url(job_id, request.generated_video_id, request.heygen_api_key)

            if source_url:
                await asyncio.to_thread(self.download_service.download, source_url, temp_original, job_id)
            elif request.source_file_path:
                source_file = Path(request.source_file_path)
                await asyncio.to_thread(self.download_service.copy_local_file, source_file, temp_original, job_id)
            else:
                raise ValueError("Either source_url, source_file_path, or generated_video_id must be provided")

            await asyncio.to_thread(self.ffmpeg_service.ensure_shorts_format, temp_original, temp_shorts, job_id)

            creds = await asyncio.to_thread(self.oauth_service.get_credentials)
            uploader = YouTubeUploadService(
                credentials=creds,
                chunk_size_mb=self.settings.upload_chunk_size_mb,
                max_retries=self.settings.max_upload_retries,
            )

            upload_result = await asyncio.to_thread(
                uploader.upload_short,
                file_path=temp_shorts,
                title=request.title,
                description=request.description,
                tags=request.tags,
                category_id=request.category_id,
                privacy_status=request.privacy_status,
                job_id=job_id,
            )

            self.store.update_status(
                job_id,
                "completed",
                youtube_video_id=upload_result["youtube_video_id"],
                youtube_url=upload_result["youtube_url"],
                retry_count=int(upload_result.get("retry_count", 0)),
            )

        except Exception as exc:
            logger.error(
                "Shorts pipeline failed",
                extra={"job_id": job_id, "stage": "pipeline"},
                exc_info=True,
            )
            self.store.update_status(job_id, "failed", error_message=str(exc))
        finally:
            await asyncio.to_thread(self.cleanup_service.cleanup_files, [temp_original, temp_shorts], job_id)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.store.get_job(job_id)

    async def _poll_heygen_for_url(self, job_id: str, generated_video_id: str, heygen_api_key: str | None) -> str:
        if not heygen_api_key:
            raise ValueError("heygen_api_key is required when generated_video_id is provided")

        from heygen_module import HeyGenClient

        heygen_client = HeyGenClient(api_key=heygen_api_key)
        poller = HygenPollingService(
            heygen_client=heygen_client,
            max_poll_seconds=self.settings.max_heygen_poll_seconds,
            poll_interval_seconds=self.settings.heygen_poll_interval_seconds,
        )
        return await asyncio.to_thread(poller.wait_for_video_url, generated_video_id, job_id)
