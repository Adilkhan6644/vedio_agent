from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    project_root: Path
    temp_dir: Path
    credentials_dir: Path
    youtube_client_secret_file: Path
    youtube_token_file: Path
    upload_db_path: Path
    upload_chunk_size_mb: int
    max_upload_retries: int
    max_download_retries: int
    max_heygen_poll_seconds: int
    heygen_poll_interval_seconds: int
    ffmpeg_path: str
    ffprobe_path: str
    youtube_default_category: str
    youtube_default_privacy: str



def _to_abs_path(project_root: Path, value: str, fallback: str) -> Path:
    raw = value.strip() if value else fallback
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    return path



def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")

    temp_dir = _to_abs_path(project_root, os.getenv("SHORTS_TEMP_DIR", "temp"), "temp")
    credentials_dir = _to_abs_path(project_root, os.getenv("SHORTS_CREDENTIALS_DIR", "credentials"), "credentials")
    youtube_client_secret_file = _to_abs_path(
        project_root,
        os.getenv("YOUTUBE_CLIENT_SECRET_FILE", str(credentials_dir / "client_secret.json")),
        str(credentials_dir / "client_secret.json"),
    )
    youtube_token_file = _to_abs_path(
        project_root,
        os.getenv("YOUTUBE_TOKEN_FILE", str(credentials_dir / "token.json")),
        str(credentials_dir / "token.json"),
    )
    upload_db_path = _to_abs_path(project_root, os.getenv("UPLOAD_DB_PATH", "app/data/uploads.db"), "app/data/uploads.db")

    temp_dir.mkdir(parents=True, exist_ok=True)
    credentials_dir.mkdir(parents=True, exist_ok=True)
    upload_db_path.parent.mkdir(parents=True, exist_ok=True)

    return Settings(
        project_root=project_root,
        temp_dir=temp_dir,
        credentials_dir=credentials_dir,
        youtube_client_secret_file=youtube_client_secret_file,
        youtube_token_file=youtube_token_file,
        upload_db_path=upload_db_path,
        upload_chunk_size_mb=int(os.getenv("YOUTUBE_UPLOAD_CHUNK_SIZE_MB", "8")),
        max_upload_retries=int(os.getenv("YOUTUBE_MAX_UPLOAD_RETRIES", "8")),
        max_download_retries=int(os.getenv("VIDEO_DOWNLOAD_MAX_RETRIES", "4")),
        max_heygen_poll_seconds=int(os.getenv("HEYGEN_MAX_POLL_SECONDS", "900")),
        heygen_poll_interval_seconds=int(os.getenv("HEYGEN_POLL_INTERVAL_SECONDS", "8")),
        ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg"),
        ffprobe_path=os.getenv("FFPROBE_PATH", "ffprobe"),
        youtube_default_category=os.getenv("YOUTUBE_DEFAULT_CATEGORY", "22"),
        youtube_default_privacy=os.getenv("YOUTUBE_DEFAULT_PRIVACY", "public"),
    )
