"""
HeyGen Video Generator Module
Uses the HeyGen v3 API to generate Photo Avatar AI videos from text scripts + public image URLs.
Served via FastAPI.

API Docs: https://developers.heygen.com/reference/create-avatar
"""

import asyncio
import os
import sys
import base64
import shutil
import requests
from io import BytesIO
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root
load_dotenv(Path(__file__).parent / ".env")

# Add agent directory to path for imports
AGENT_DIR = Path(__file__).parent / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

FOLLOW_BOT_DIR = Path(__file__).parent / "automated_follow"
if str(FOLLOW_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(FOLLOW_BOT_DIR))

from automated_follow.ig_bot import run_instagram_follow_bot
from automated_follow.comments import run_instagram_comment_bot
from automated_follow.engagement_agent import run_instagram_profile_engagement_bot

# Import agent functions (will work if .env has GROQ_API_KEY and SERPER_API_KEY)
try:
    from agent.research_agent import run_solution_agent, run_script_agent, run_rating_agent, search_web
    AGENTS_AVAILABLE = True
except Exception as e:
    print(f"[WARNING] Agents not available: {e}")
    AGENTS_AVAILABLE = False

BASE_URL = "https://api.heygen.com"

# ── Default Avatar Configuration ───────────────────────────────────────────
DEFAULT_AVATAR_IMAGE_URL = "https://i.imageupload.app/3af33f94d36ff1041b7a.jpeg"
AVATAR_CACHE_FILE = Path(__file__).parent / ".avatar_cache.json"


def get_cached_avatar_id() -> str | None:
    """Get cached avatar ID if it exists."""
    if AVATAR_CACHE_FILE.exists():
        try:
            import json
            with open(AVATAR_CACHE_FILE, "r") as f:
                cache = json.load(f)
                return cache.get("avatar_id")
        except Exception:
            return None
    return None


def save_avatar_cache(avatar_id: str):
    """Save avatar ID to cache file."""
    import json
    with open(AVATAR_CACHE_FILE, "w") as f:
        json.dump({"avatar_id": avatar_id, "image_url": DEFAULT_AVATAR_IMAGE_URL}, f)


def clear_avatar_cache():
    """Clear the avatar cache to force recreation."""
    if AVATAR_CACHE_FILE.exists():
        AVATAR_CACHE_FILE.unlink()
        print("[INFO] Avatar cache cleared")


def get_or_create_default_avatar(api_key: str) -> str:
    cached_id = get_cached_avatar_id()
    if cached_id:
        print(f"[INFO] Using cached avatar: {cached_id}")
        return cached_id
    
    print(f"[INFO] Creating new avatar from default image...")
    client = HeyGenClient(api_key=api_key)
    avatar_id = client.create_photo_avatar_from_url(
        image_url=DEFAULT_AVATAR_IMAGE_URL,
        name="Default Agent Avatar"
    )
    
    # ✅ Wait for avatar to finish processing before caching/using
    print(f"[INFO] Waiting for avatar {avatar_id} to finish processing...")
    client.wait_for_avatar_ready(avatar_id)
    
    save_avatar_cache(avatar_id)
    print(f"[INFO] Avatar ready and cached: {avatar_id}")
    return avatar_id


class HeyGenClient:
    """Client wrapper for the HeyGen v3 API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("HEYGEN_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "HeyGen API key is required. Pass it directly or set HEYGEN_API_KEY in .env"
            )
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    # ── Verify / Get Voices ──────────────────────────────────────────────
    def get_voices(self) -> dict:
        """
        Fetch the list of available voices via v3 API.
        Also acts as API key verification.
        Returns: A dict with a voices list.
        """
        resp = requests.get(
            f"{BASE_URL}/v3/voices",
            headers=self.headers,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("data", resp.json())

    # ── Step 1+2: Create Photo Avatar from Public URL ──────────────────
    def create_photo_avatar_from_url(
        self, image_url: str, name: str = "My Photo Avatar"
    ) -> str:
        """
        Create a Photo Avatar from a publicly accessible image URL.

        RECOMMENDED METHOD: Direct URL input avoids file upload issues.
        HeyGen fetches the image from the URL and auto-detects dimensions.

        Args:
            image_url: Publicly accessible image URL (https only, no auth required)
                       Examples: https://ibb.co/dwv2KjwW, https://example.com/photo.jpg
                       Supports: PNG, JPEG, WebP formats
            name: Avatar display name

        Returns: avatar_id string.
        """
        # Validate URL format
        if not image_url.startswith("http://") and not image_url.startswith("https://"):
            raise ValueError("Image URL must start with http:// or https://")

        if len(image_url) < 10:
            raise ValueError("Image URL appears invalid (too short)")

        payload = {
            "type": "photo",
            "name": name,
            "file": {
                "type": "url",
                "url": image_url,
            },
        }

        resp = requests.post(
            f"{BASE_URL}/v3/avatars",
            headers=self.headers,
            json=payload,
            timeout=120,
        )

        if resp.status_code != 200:
            try:
                error_detail = resp.json().get("message", resp.text)
            except:
                error_detail = resp.text
            raise RuntimeError(
                f"HeyGen avatar creation failed ({resp.status_code}): {error_detail}"
            )

        data = resp.json()
        if data.get("code") and data["code"] != 100:
            error_msg = data.get("message", str(data))
            raise RuntimeError(f"HeyGen avatar creation error: {error_msg}")

        avatar_id = (
            data.get("data", {}).get("avatar_item", {}).get("id")
            or data.get("data", {}).get("id")
        )
        if not avatar_id:
            raise RuntimeError(f"No avatar_id in creation response: {data}")
        return avatar_id

    def wait_for_avatar_ready(self, avatar_id: str, timeout: int = 120, poll_interval: int = 5) -> dict:
        """
        Poll avatar status until it's ready or timeout is reached.
        The avatar needs time to process image dimensions and face detection.
        """
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = requests.get(
                f"{BASE_URL}/v2/photo_avatar/{avatar_id}",
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})

            status = data.get("status", "").lower()
            print(f"[INFO] Avatar {avatar_id} status: {status}")

            if status in ("completed", "ready", "active"):
                return data
            elif status in ("failed", "error"):
                raise RuntimeError(f"Avatar processing failed: {data}")

            time.sleep(poll_interval)

        raise TimeoutError(f"Avatar {avatar_id} did not become ready within {timeout}s")

    # ── Step 3: Generate Video ───────────────────────────────────────────
    def create_photo_avatar_video(
        self,
        avatar_id: str,
        script: str,
        voice_id: str,
        resolution: str = "1080p",
        aspect_ratio: str = "16:9",
        expressiveness: str = "medium",
        motion_prompt: str | None = None,
        title: str = "HeyGen Photo Avatar Video",
    ) -> dict:
        """
        Generate a Photo Avatar video using HeyGen v3 API.

        Args:
            avatar_id:      The photo avatar ID from create_photo_avatar().
            script:         The spoken text — controls video duration (~130 wpm).
                            For ~20 seconds, write ~43-45 words.
            voice_id:       Voice ID from get_voices().
            resolution:     "4k", "1080p", or "720p".
            aspect_ratio:   "16:9" or "9:16".
            expressiveness: "high", "medium", or "low".
            motion_prompt:  Optional natural-language motion hint, e.g. "nodding gently".
            title:          Display name in the HeyGen dashboard.

        Returns: A dict with video_id.
        """
        payload = {
            "type": "avatar",
            "avatar_id": avatar_id,
            "script": script,
            "voice_id": voice_id,
            "title": title,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "expressiveness": expressiveness,
        }

        if motion_prompt:
            payload["motion_prompt"] = motion_prompt

        resp = requests.post(
            f"{BASE_URL}/v3/videos",
            headers=self.headers,
            json=payload,
            timeout=60,
        )

        if resp.status_code != 200:
            try:
                error_detail = resp.json().get("message", resp.text)
            except:
                error_detail = resp.text
            raise RuntimeError(
                f"HeyGen video generation failed ({resp.status_code}): {error_detail}"
            )

        data = resp.json()
        if data.get("code") and data["code"] != 100:
            error_msg = data.get("message", str(data))
            raise RuntimeError(f"HeyGen video generation error: {error_msg}")
        return data.get("data", data)

    # ── Step 4: Poll Video Status ────────────────────────────────────────
    def get_video_status(self, video_id: str) -> dict:
        """
        Poll the status of a video by its video_id via v3 API.
        Statuses: pending → processing → completed | failed
        Returns: Full video data dict including video_url when completed.
        """
        resp = requests.get(
            f"{BASE_URL}/v3/videos/{video_id}",
            headers=self.headers,
            timeout=30,
        )
        
        if resp.status_code != 200:
            try:
                error_detail = resp.json().get("message", resp.text)
            except:
                error_detail = resp.text
            raise RuntimeError(f"Failed to get video status ({resp.status_code}): {error_detail}")
        
        return resp.json().get("data", resp.json())


# ═══════════════════════════════════════════════════════════════════════════
#  FastAPI Server — serves the frontend & proxies HeyGen API calls
# ═══════════════════════════════════════════════════════════════════════════

def _run_instagram_bot_wrapper(search_query, max_follows, username, password, headless):
    """Module-level wrapper for ProcessPoolExecutor (must be pickleable)."""
    return run_instagram_follow_bot(
        search_query=search_query,
        max_follows=max_follows,
        username=username,
        password=password,
        headless=headless,
        save_csv=False,
    )


def _run_instagram_comments_wrapper(search_query, max_follows, username, password, headless):
    """Module-level wrapper for ProcessPoolExecutor (must be pickleable)."""
    return run_instagram_comment_bot(
        search_query=search_query,
        max_follows=max_follows,
        username=username,
        password=password,
        headless=headless,
        save_csv=False,
    )


def _run_instagram_profile_engagement_wrapper(
    target_username,
    max_posts,
    username,
    password,
    headless,
    comment_each_post,
    like_each_post,
):
    """Module-level wrapper for ProcessPoolExecutor (must be pickleable)."""
    return run_instagram_profile_engagement_bot(
        target_username=target_username,
        max_posts=max_posts,
        username=username,
        password=password,
        headless=headless,
        comment_each_post=comment_each_post,
        like_each_post=like_each_post,
        save_csv=False,
    )


def create_app():
    """Create and configure the FastAPI application."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse, FileResponse
    from pydantic import BaseModel
    
    try:
        from app.routes.shorts import public_router as shorts_public_router
        from app.routes.shorts import router as shorts_router
    except Exception as import_error:
        shorts_router = None
        shorts_public_router = None
        print(f"[WARNING] Shorts router unavailable: {import_error}")

    app = FastAPI(
        title="HeyGen Photo Avatar Video Generator",
        version="2.0.0",
        openapi_tags=[
            {"name": "Instagram Automated Follow", "description": "Instagram profile discovery and follow automation endpoints."},
            {"name": "Instagram Automated Comments", "description": "Instagram comment automation endpoints from automated_follow/comments.py."},
            {"name": "Instagram Profile Engagement", "description": "Instagram target-profile engagement endpoint from automated_follow/engagement_agent.py."},
        ],
    )

    if shorts_router is not None:
        app.include_router(shorts_router)
    if shorts_public_router is not None:
        app.include_router(shorts_public_router)

    # ── Pydantic models ───────────────────────────────────────────────
    class VerifyKeyRequest(BaseModel):
        api_key: str

    class CreateAvatarRequest(BaseModel):
        api_key: str
        image_url: str

    class GenerateRequest(BaseModel):
        api_key: str
        script: str
        voice_id: str
        avatar_id: str
        resolution: str = "1080p"
        aspect_ratio: str = "16:9"
        expressiveness: str = "medium"
        motion_prompt: str | None = None

    class InstagramFollowRequest(BaseModel):
        search_query: str = "fitness coach"
        max_follows: int = 5
        username: str | None = None
        password: str | None = None
        headless: bool = True

    class InstagramCommentsRequest(BaseModel):
        search_query: str = "fitness coach"
        max_follows: int = 5
        username: str | None = None
        password: str | None = None
        headless: bool = True

    class InstagramProfileEngagementRequest(BaseModel):
        target_username: str
        max_posts: int = 5
        username: str | None = None
        password: str | None = None
        headless: bool = True
        comment_each_post: bool = True
        like_each_post: bool = True

    # ── Serve frontend ───────────────────────────────────────────────
    @app.get("/")
    async def index():
        return FileResponse(Path(__file__).parent / "index.html")

    @app.get("/style.css")
    async def styles():
        return FileResponse(
            Path(__file__).parent / "style.css",
            media_type="text/css",
        )

    # ── API: Verify key / Get Voices ─────────────────────────────────
    @app.post("/api/verify-key")
    async def api_verify_key(body: VerifyKeyRequest):
        try:
            client = HeyGenClient(api_key=body.api_key)
            voices_data = client.get_voices()
            return {"success": True, "data": voices_data}
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": str(e)},
            )

    # ── API: Create avatar from URL ──────────────────────────────────
    @app.post("/api/create-avatar")
    async def api_create_avatar(body: CreateAvatarRequest):
        if not body.api_key:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "API key is required"},
            )
        if not body.image_url:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "image_url is required"},
            )

        try:
            client = HeyGenClient(api_key=body.api_key)

            # Create avatar directly from URL (no file upload needed!)
            avatar_id = client.create_photo_avatar_from_url(
                image_url=body.image_url,
                name=f"Avatar from {body.image_url.split('/')[-1]}",
            )

            return {
                "success": True,
                "data": {
                    "avatar_id": avatar_id,
                },
            }
        except ValueError as e:
            # Handle validation errors
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": str(e)},
            )
        except RuntimeError as e:
            # Handle HeyGen API errors
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": str(e)},
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Server error: {str(e)}"},
            )

    # ── API: Generate video ──────────────────────────────────────────
    @app.post("/api/generate")
    async def api_generate(body: GenerateRequest):
        if not body.api_key:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "API key is required"},
            )
        if not body.script or not body.voice_id or not body.avatar_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "script, voice_id, and avatar_id are all required"},
            )

        # Validate script length (HeyGen max is 5,000 characters)
        if len(body.script) > 5000:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Script too long. Max 5,000 characters."},
            )

        try:
            client = HeyGenClient(api_key=body.api_key)
            result = client.create_photo_avatar_video(
                avatar_id=body.avatar_id,
                script=body.script,
                voice_id=body.voice_id,
                resolution=body.resolution,
                aspect_ratio=body.aspect_ratio,
                expressiveness=body.expressiveness,
                motion_prompt=body.motion_prompt,
            )
            return {"success": True, "data": result}
        except RuntimeError as e:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": str(e)},
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Server error: {str(e)}"},
            )

    @app.post("/api/instagram/follow", tags=["Instagram Automated Follow"])
    async def api_instagram_follow(body: InstagramFollowRequest):
        try:
            from concurrent.futures import ProcessPoolExecutor
            loop = asyncio.get_running_loop()
            with ProcessPoolExecutor(max_workers=1) as executor:
                result = await loop.run_in_executor(
                    executor,
                    _run_instagram_bot_wrapper,
                    body.search_query,
                    body.max_follows,
                    body.username,
                    body.password,
                    body.headless,
                )
            return {
                "success": True,
                "data": {
                    "collected_profiles": result.get("collected_profiles", []),
                    "followed_profiles": result.get("followed_profiles", []),
                },
            }
        except Exception as e:
            import traceback
            print(f"[ERROR] Instagram follow failed:\n{traceback.format_exc()}")
            error_detail = str(e) or e.__class__.__name__
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Instagram follow error: {error_detail}"},
            )

    @app.post("/api/instagram/comments", tags=["Instagram Automated Comments"])
    async def api_instagram_comments(body: InstagramCommentsRequest):
        try:
            from concurrent.futures import ProcessPoolExecutor
            loop = asyncio.get_running_loop()
            with ProcessPoolExecutor(max_workers=1) as executor:
                result = await loop.run_in_executor(
                    executor,
                    _run_instagram_comments_wrapper,
                    body.search_query,
                    body.max_follows,
                    body.username,
                    body.password,
                    body.headless,
                )
            return {
                "success": True,
                "data": {
                    "collected_profiles": result.get("collected_profiles", []),
                    "followed_profiles": result.get("followed_profiles", []),
                    "comments": result.get("comments", []),
                },
            }
        except Exception as e:
            import traceback
            print(f"[ERROR] Instagram comments failed:\n{traceback.format_exc()}")
            error_detail = str(e) or e.__class__.__name__
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Instagram comments error: {error_detail}"},
            )

    @app.post("/api/instagram/profile-engagement", tags=["Instagram Profile Engagement"])
    async def api_instagram_profile_engagement(body: InstagramProfileEngagementRequest):
        try:
            from concurrent.futures import ProcessPoolExecutor
            loop = asyncio.get_running_loop()
            with ProcessPoolExecutor(max_workers=1) as executor:
                result = await loop.run_in_executor(
                    executor,
                    _run_instagram_profile_engagement_wrapper,
                    body.target_username,
                    body.max_posts,
                    body.username,
                    body.password,
                    body.headless,
                    body.comment_each_post,
                    body.like_each_post,
                )
            return {
                "success": True,
                "data": {
                    "profile_url": result.get("profile_url", ""),
                    "total_posts_collected": result.get("total_posts_collected", 0),
                    "results": result.get("results", []),
                },
            }
        except Exception as e:
            import traceback
            print(f"[ERROR] Instagram profile engagement failed:\n{traceback.format_exc()}")
            error_detail = str(e) or e.__class__.__name__
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Instagram profile engagement error: {error_detail}"},
            )

    # ── API: Check video status ──────────────────────────────────────
    @app.get("/api/status/{video_id}")
    async def api_status(video_id: str, api_key: str):
        if not api_key:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "API key is required"},
            )
        try:
            client = HeyGenClient(api_key=api_key)
            result = client.get_video_status(video_id)
            return {"success": True, "data": result}
        except RuntimeError as e:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": str(e)},
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Server error: {str(e)}"},
            )

    # ═══════════════════════════════════════════════════════════════════
    #  AGENT PIPELINE ENDPOINTS
    # ═══════════════════════════════════════════════════════════════════

    class AgentPipelineRequest(BaseModel):
        topic: str

    class WebSearchRequest(BaseModel):
        query: str

    # ── API: Run full agent pipeline ─────────────────────────────────
    @app.post("/api/agents/pipeline")
    async def api_agent_pipeline(body: AgentPipelineRequest):
        """Run the full agent pipeline: web search → solution → script → rating."""
        if not AGENTS_AVAILABLE:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "Agents not available. Check GROQ_API_KEY and SERPER_API_KEY in .env"},
            )
        if not body.topic:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "topic is required"},
            )

        try:
            # Step 1: Web Search
            search_results = search_web(body.topic)

            # Step 2: Solution Research
            solution = run_solution_agent(body.topic)

            # Step 3: Script Writing
            script = run_script_agent(body.topic, solution)

            # Step 4: Rating & Optimization
            result = run_rating_agent(script)

            return {
                "success": True,
                "data": {
                    "topic": body.topic,
                    "search_results": search_results,
                    "solution": solution,
                    "original_script": script,
                    "scores": result["scores"],
                    "feedback": result["feedback"],
                    "final_script": result["optimized_script"],
                }
            }
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Pipeline error: {str(e)}"},
            )

    # ── API: Web Search only ─────────────────────────────────────────
    @app.post("/api/agents/search")
    async def api_web_search(body: WebSearchRequest):
        """Run web search for a query."""
        if not AGENTS_AVAILABLE:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "Agents not available. Check GROQ_API_KEY and SERPER_API_KEY in .env"},
            )
        if not body.query:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "query is required"},
            )

        try:
            results = search_web(body.query)
            return {"success": True, "data": {"query": body.query, "results": results}}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Search error: {str(e)}"},
            )

    # ── API: Solution Agent only ─────────────────────────────────────
    @app.post("/api/agents/solution")
    async def api_solution_agent(body: AgentPipelineRequest):
        """Run solution research agent for a topic."""
        if not AGENTS_AVAILABLE:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "Agents not available. Check GROQ_API_KEY and SERPER_API_KEY in .env"},
            )
        if not body.topic:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "topic is required"},
            )

        try:
            search_results = search_web(body.topic)
            solution = run_solution_agent(body.topic)
            return {
                "success": True,
                "data": {
                    "topic": body.topic,
                    "search_results": search_results,
                    "solution": solution,
                }
            }
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Solution agent error: {str(e)}"},
            )

    # ── API: Script Agent only ───────────────────────────────────────
    class ScriptRequest(BaseModel):
        topic: str
        solution: str

    @app.post("/api/agents/script")
    async def api_script_agent(body: ScriptRequest):
        """Run script writing agent with a topic and solution."""
        if not AGENTS_AVAILABLE:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "Agents not available. Check GROQ_API_KEY and SERPER_API_KEY in .env"},
            )
        if not body.topic or not body.solution:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "topic and solution are required"},
            )

        try:
            script = run_script_agent(body.topic, body.solution)
            return {"success": True, "data": {"topic": body.topic, "script": script}}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Script agent error: {str(e)}"},
            )

    # ── API: Rating Agent only ───────────────────────────────────────
    class RatingRequest(BaseModel):
        script: str

    @app.post("/api/agents/rating")
    async def api_rating_agent(body: RatingRequest):
        """Run rating agent on a script."""
        if not AGENTS_AVAILABLE:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "Agents not available. Check GROQ_API_KEY and SERPER_API_KEY in .env"},
            )
        if not body.script:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "script is required"},
            )

        try:
            result = run_rating_agent(body.script)
            return {"success": True, "data": result}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Rating agent error: {str(e)}"},
            )

    # ── API: Full Pipeline + Video Generation (with default avatar) ──
    class FullVideoRequest(BaseModel):
        topic: str
        api_key: str | None = None
        voice_id: str = "en-US-Standard-C"  # Default voice
        resolution: str = "1080p"
        aspect_ratio: str = "16:9"
        expressiveness: str = "medium"

    @app.post("/api/agents/generate-video")
    async def api_generate_video_with_agents(body: FullVideoRequest):
        """Run full agent pipeline and generate video with default cached avatar."""
        if not AGENTS_AVAILABLE:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "Agents not available. Check GROQ_API_KEY and SERPER_API_KEY in .env"},
            )
        
        api_key = body.api_key or os.getenv("HEYGEN_API_KEY", "")
        if not api_key:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "HeyGen API key required. Pass in request or set HEYGEN_API_KEY in .env"},
            )
        
        if not body.topic:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "topic is required"},
            )

        try:
            # Step 1-4: Run Agent Pipeline
            print(f"\n🔍 Running agent pipeline for: {body.topic}")
            
            search_results = search_web(body.topic)
            solution = run_solution_agent(body.topic)
            script = run_script_agent(body.topic, solution)
            rating_result = run_rating_agent(script)
            
            final_script = rating_result["optimized_script"]
            print(f"\n✅ Final script generated ({len(final_script)} chars)")

            # Step 5: Get or create default avatar (with retry on dimension error)
            avatar_id = get_or_create_default_avatar(api_key)

            # Step 6: Generate video (with retry if avatar has issues)
            print(f"\n🎬 Generating video with avatar: {avatar_id}")
            client = HeyGenClient(api_key=api_key)
            
            try:
                video_result = client.create_photo_avatar_video(
                    avatar_id=avatar_id,
                    script=final_script,
                    voice_id=body.voice_id,
                    resolution=body.resolution,
                    aspect_ratio=body.aspect_ratio,
                    expressiveness=body.expressiveness,
                    title=f"Agent Video: {body.topic[:50]}"
                )
            except RuntimeError as e:
                if "missing image dimensions" in str(e).lower():
                    print(f"[WARNING] Avatar has dimension issues, recreating...")
                    clear_avatar_cache()
                    avatar_id = get_or_create_default_avatar(api_key)
                    print(f"[INFO] Retrying video with new avatar: {avatar_id}")
                    video_result = client.create_photo_avatar_video(
                        avatar_id=avatar_id,
                        script=final_script,
                        voice_id=body.voice_id,
                        resolution=body.resolution,
                        aspect_ratio=body.aspect_ratio,
                        expressiveness=body.expressiveness,
                        title=f"Agent Video: {body.topic[:50]}"
                    )
                else:
                    raise

            return {
                "success": True,
                "data": {
                    "topic": body.topic,
                    "search_results": search_results,
                    "solution": solution,
                    "original_script": script,
                    "scores": rating_result["scores"],
                    "feedback": rating_result["feedback"],
                    "final_script": final_script,
                    "avatar_id": avatar_id,
                    "video": video_result
                }
            }
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[ERROR] Pipeline/Video generation failed:\n{error_detail}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Pipeline/Video error: {str(e)}"},
            )

    # ── API: Fetch Video URL or Stream Video ───────────────────────────
    @app.get("/api/video/{video_id}")
    async def api_get_video(video_id: str, api_key: str | None = None):
        """
        Get video URL or stream video by video_id.
        Returns video URL if available, or video data including status.
        """
        api_key = api_key or os.getenv("HEYGEN_API_KEY", "")
        if not api_key:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "HeyGen API key required. Pass as query param or set HEYGEN_API_KEY in .env"},
            )

        try:
            client = HeyGenClient(api_key=api_key)
            video_data = client.get_video_status(video_id)

            video_url = video_data.get("video_url") or video_data.get("url") or video_data.get("download_url")

            if video_url:
                return {
                    "success": True,
                    "data": {
                        "video_id": video_id,
                        "status": video_data.get("status"),
                        "video_url": video_url,
                        "full_data": video_data
                    }
                }
            else:
                return {
                    "success": True,
                    "data": {
                        "video_id": video_id,
                        "status": video_data.get("status", "unknown"),
                        "message": "Video is not ready yet. Check status.",
                        "full_data": video_data
                    }
                }
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Failed to fetch video: {str(e)}"},
            )

    @app.get("/api/video/{video_id}/stream")
    async def api_stream_video(video_id: str, api_key: str | None = None):
        """
        Stream the video directly if ready. Returns video file content.
        """
        from fastapi.responses import StreamingResponse
        import httpx

        api_key = api_key or os.getenv("HEYGEN_API_KEY", "")
        if not api_key:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "HeyGen API key required. Pass as query param or set HEYGEN_API_KEY in .env"},
            )

        try:
            client = HeyGenClient(api_key=api_key)
            video_data = client.get_video_status(video_id)

            video_url = video_data.get("video_url") or video_data.get("url") or video_data.get("download_url")

            if not video_url:
                return JSONResponse(
                    status_code=202,
                    content={"success": False, "message": "Video is not ready yet", "status": video_data.get("status")},
                )

            async with httpx.AsyncClient() as httpx_client:
                resp = await httpx_client.get(video_url, timeout=60)
                resp.raise_for_status()

                return StreamingResponse(
                    iter([resp.content]),
                    media_type="video/mp4",
                    headers={
                        "Content-Disposition": f'attachment; filename="{video_id}.mp4"'
                    }
                )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Failed to stream video: {str(e)}"},
            )

    return app


# ── Entry point ──────────────────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    import uvicorn

    print("\n  [*] HeyGen Photo Avatar Video Generator (v3 API)")
    print("  --------------------------------------------------")
    print("  Open http://localhost:8000 in your browser\n")
    uvicorn.run("heygen_module:app", host="0.0.0.0", port=8000, reload=True)