# YouTube Shorts Pipeline

## 1) Install dependencies

```bash
pip install -r requirements.txt
```

## 2) Configure environment variables

Add these to `.env` as needed:

- `YOUTUBE_CLIENT_SECRET_FILE=credentials/client_secret.json`
- `YOUTUBE_TOKEN_FILE=credentials/token.json`
- `YOUTUBE_UPLOAD_CHUNK_SIZE_MB=8`
- `YOUTUBE_MAX_UPLOAD_RETRIES=8`
- `VIDEO_DOWNLOAD_MAX_RETRIES=4`
- `HEYGEN_MAX_POLL_SECONDS=900`
- `HEYGEN_POLL_INTERVAL_SECONDS=8`
- `FFMPEG_PATH=ffmpeg`
- `FFPROBE_PATH=ffprobe`
- `YOUTUBE_DEFAULT_CATEGORY=22`
- `YOUTUBE_DEFAULT_PRIVACY=public`
- `UPLOAD_DB_PATH=app/data/uploads.db`

## 3) Run one-time OAuth setup

Place your OAuth desktop client JSON at `credentials/client_secret.json`, then run:

```bash
python -m app.utils.oauth_setup
```

This creates `credentials/token.json` with refresh token support.

## 4) Start the API

Current project entrypoint:

```bash
uvicorn heygen_module:app --reload
```

Alternative Shorts-only app:

```bash
uvicorn app.main:app --reload
```

## 5) API flow

### Create background upload job

`POST /generate-short` or `POST /api/shorts/generate-short`

Sample payload:

```json
{
  "generated_video_id": "heygen-video-id",
  "heygen_api_key": "YOUR_HEYGEN_API_KEY",
  "title": "5 AI Productivity Tips",
  "description": "Quick tips for founders",
  "tags": ["ai", "productivity", "startup"],
  "privacy_status": "public"
}
```

You can also send either:

- `source_url`: direct MP4 URL
- `source_file_path`: local MP4 path

### Check upload status

`GET /generate-short/{job_id}` or `GET /api/shorts/jobs/{job_id}`

On completion, response includes:

- `youtube_video_id`
- `youtube_url`
- `short_url`
