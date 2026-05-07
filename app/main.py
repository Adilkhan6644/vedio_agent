from __future__ import annotations

from fastapi import FastAPI

from app.routes.shorts import public_router as shorts_public_router
from app.routes.shorts import router as shorts_router


app = FastAPI(title="YouTube Shorts Pipeline API", version="1.0.0")
app.include_router(shorts_router)
app.include_router(shorts_public_router)
