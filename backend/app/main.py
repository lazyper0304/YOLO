"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core.database import engine
from app.core.redis_client import init_redis, close_redis
from app.utils.file_utils import create_upload_directories
from app.services.task_queue import TaskQueue
from app.models.user import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize services on startup, cleanup on shutdown."""
    # Startup
    create_upload_directories()

    # Set project-local temp directory
    os.environ["TMPDIR"] = settings.temp_dir
    os.environ["TEMP"] = settings.temp_dir
    os.environ["TMP"] = settings.temp_dir

    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize Redis
    try:
        await init_redis()
    except Exception:
        print("Warning: Redis connection failed, caching will be disabled")

    # Start background task queue
    try:
        task_queue = TaskQueue()
        await task_queue.start()
    except Exception as e:
        print(f"Warning: Task queue start failed: {e}")

    # Pre-download default YOLO models in background
    try:
        from app.services.yolo_service import YOLOService
        yolo = YOLOService()
        await yolo.pre_download_models()
    except Exception as e:
        print(f"Warning: YOLO model pre-download failed: {e}")

    yield

    # Shutdown
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="YOLO Detection Platform",
    description="Image object detection and analysis platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from fastapi import HTTPException
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "message": exc.detail, "data": None},
        )
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": f"Internal server error: {str(exc)}", "data": None},
    )


uploads_path = Path(settings.UPLOAD_DIR)
if uploads_path.exists():
    app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")


@app.get("/api/health")
async def health_check():
    return {"code": 0, "message": "ok", "data": {"status": "healthy"}}


from app.api.auth import router as auth_router
from app.api.llm_config import router as llm_config_router
from app.api.yolo_models import router as yolo_models_router
from app.api.detection import router as detection_router
from app.api.history import router as history_router
from app.api.system import router as system_router
from app.api.dashboard import router as dashboard_router
from app.api.tasks import router as tasks_router
from app.api.chat import router as chat_router

app.include_router(auth_router)
app.include_router(llm_config_router)
app.include_router(yolo_models_router)
app.include_router(detection_router)
app.include_router(history_router)
app.include_router(system_router)
app.include_router(dashboard_router)
app.include_router(tasks_router)

app.include_router(chat_router)
