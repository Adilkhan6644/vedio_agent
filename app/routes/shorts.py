from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.workers.pipeline_worker import ShortsPipelineWorker, UploadJobRequest


router = APIRouter(prefix="/api/shorts", tags=["YouTube Shorts"])
public_router = APIRouter(tags=["YouTube Shorts"])
worker = ShortsPipelineWorker()
settings = get_settings()


def _normalize_privacy_status(value: str) -> str:
    if value not in {"public", "private", "unlisted"}:
        return "public"
    return value


class GenerateShortRequest(BaseModel):
    generated_video_id: str | None = Field(default=None, description="HeyGen generated video id")
    source_url: str | None = Field(default=None, description="Direct downloadable MP4 URL")
    source_file_path: str | None = Field(default=None, description="Local MP4 path produced by generator")
    heygen_api_key: str | None = Field(default=None, description="Required when generated_video_id is used")

    title: str = Field(..., max_length=100)
    description: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    category_id: str = Field(default_factory=lambda: settings.youtube_default_category)
    privacy_status: Literal["public", "private", "unlisted"] = Field(default_factory=lambda: _normalize_privacy_status(settings.youtube_default_privacy))


class GenerateShortResponse(BaseModel):
    job_id: str
    status: str


async def _enqueue_generate_short(body: GenerateShortRequest, background_tasks: BackgroundTasks):
    if not body.generated_video_id and not body.source_url and not body.source_file_path:
        raise HTTPException(
            status_code=400,
            detail="Provide one of generated_video_id, source_url, or source_file_path",
        )

    request = UploadJobRequest(
        generated_video_id=body.generated_video_id,
        source_url=body.source_url,
        source_file_path=body.source_file_path,
        title=body.title,
        description=body.description,
        tags=body.tags,
        category_id=body.category_id,
        privacy_status=body.privacy_status,
        heygen_api_key=body.heygen_api_key,
    )

    job_id = worker.create_job(request)
    background_tasks.add_task(worker.process_job, job_id, request)
    return GenerateShortResponse(job_id=job_id, status="queued")


async def _get_job_status(job_id: str):
    job = worker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") == "completed":
        return {
            **job,
            "short_url": f"https://youtube.com/shorts/{job.get('youtube_video_id')}" if job.get("youtube_video_id") else None,
        }

    return job


@router.post("/generate-short", response_model=GenerateShortResponse)
async def generate_short_api(body: GenerateShortRequest, background_tasks: BackgroundTasks):
    return await _enqueue_generate_short(body, background_tasks)


@public_router.post("/generate-short", response_model=GenerateShortResponse, include_in_schema=False)
async def generate_short_public(body: GenerateShortRequest, background_tasks: BackgroundTasks):
    return await _enqueue_generate_short(body, background_tasks)


@router.get("/jobs/{job_id}")
async def get_job_status_api(job_id: str):
    return await _get_job_status(job_id)


@public_router.get("/generate-short/{job_id}", include_in_schema=False)
async def get_job_status_public(job_id: str):
    return await _get_job_status(job_id)
