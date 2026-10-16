"""The local web app: one page and a tiny JSON API.

GET  /api/status   what's ready (Jev key present? model downloaded / loaded?)
POST /api/warmup   load the local model in the background
POST /api/ask      {headline, model: "jev" | "anyjev" | "raw", swapped: bool} -> one decision
"""
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import models
from .config import settings

STATIC = Path(__file__).parent / "static"
MAX_LEN = 300

app = FastAPI(title="Onion or Not", docs_url=None, redoc_url=None)
_pool = ThreadPoolExecutor(max_workers=4)


@app.middleware("http")
async def no_cache(request, call_next):
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    return dict(jev=models.jev.status(), local=models.local.status(),
                question=models.QUESTION, options=models.OPTIONS)


@app.post("/api/warmup")
def warmup():
    st = models.local.status()
    if st.get("ready") and not st.get("loaded") and not st.get("loading"):
        threading.Thread(target=lambda: _quiet(models.local.load), daemon=True).start()
    return models.local.status()


def _quiet(fn):
    try:
        fn()
    except Exception:
        pass        # the error is kept in local.load_error and shown by /api/status


class AskReq(BaseModel):
    headline: str = Field(min_length=1, max_length=MAX_LEN)
    model: str
    swapped: bool = False


@app.post("/api/ask")
async def ask(req: AskReq):
    headline = " ".join(req.headline.split())
    if not headline:
        return JSONResponse({"error": "Type a headline first."}, status_code=400)
    if req.model not in ("jev", "anyjev", "raw"):
        return JSONResponse({"error": "Unknown model."}, status_code=400)
    try:
        res = await asyncio.get_running_loop().run_in_executor(_pool, models.ask, req.model, headline, req.swapped)
        return dict(res, answer=max(models.OPTIONS, key=lambda o: res["probs"][o]), swapped=req.swapped)
    except Exception as e:
        return JSONResponse({"error": _friendly(e)}, status_code=502)


def _friendly(e: Exception) -> str:
    name, msg = type(e).__name__, str(e)
    if "Authentication" in name or "401" in msg:
        return "TypeSafe didn't accept the API key. Check TYPESAFE_API_KEY in .env, then restart."
    if "RateLimit" in name or "429" in msg:
        return "TypeSafe's rate limit was hit. Wait a moment and try again."
    if "Connection" in name or "Timeout" in name:
        return "Couldn't reach TypeSafe's API. Check your internet connection."
    return f"{name}: {msg[:240]}"


app.mount("/static", StaticFiles(directory=STATIC), name="static")
