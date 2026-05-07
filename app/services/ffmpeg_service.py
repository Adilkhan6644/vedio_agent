from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.logging_utils import get_logger


logger = get_logger(__name__)


class FfmpegService:
    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def get_video_info(self, source_path: Path) -> dict:
        cmd = [
            self.ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "stream=width,height:format=duration,format_name",
            "-of",
            "json",
            str(source_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout or "{}")

        streams = data.get("streams", [])
        stream = streams[0] if streams else {}
        fmt = data.get("format", {})

        duration = float(fmt.get("duration", 0.0))
        width = int(stream.get("width", 0) or 0)
        height = int(stream.get("height", 0) or 0)

        return {
            "duration": duration,
            "width": width,
            "height": height,
            "format_name": fmt.get("format_name", ""),
        }

    def ensure_shorts_format(self, source_path: Path, output_path: Path, job_id: str) -> tuple[Path, dict]:
        info = self.get_video_info(source_path)

        logger.info(
            "Preparing Shorts conversion",
            extra={"job_id": job_id, "stage": "ffmpeg", "duration": info["duration"]},
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        filter_chain = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(source_path),
            "-vf",
            filter_chain,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-r",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            "-ar",
            "44100",
            "-movflags",
            "+faststart",
            "-t",
            "60",
            str(output_path),
        ]

        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg conversion failed: {process.stderr.strip()}")

        output_info = self.get_video_info(output_path)
        self._validate_shorts_video(output_info)
        return output_path, output_info

    @staticmethod
    def _validate_shorts_video(info: dict) -> None:
        width = info.get("width", 0)
        height = info.get("height", 0)
        duration = info.get("duration", 0)

        if width <= 0 or height <= 0:
            raise RuntimeError("Invalid output dimensions from FFmpeg")
        if height < width:
            raise RuntimeError("Output video is not vertical")
        if duration <= 0:
            raise RuntimeError("Output video duration is invalid")
        if duration > 60.5:
            raise RuntimeError("Output video exceeds Shorts duration limit")
