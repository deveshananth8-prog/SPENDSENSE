"""SpendSense AI FastAPI entrypoint (Stage 1: UI Shell & Hard-coded Sample Data)."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import pages

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(pages.router)


@app.get("/health")
async def health():
    return {"status": "ok", "stage": 1}
