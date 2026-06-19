"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core import engine, init_redis, close_redis
from app.core.database import async_session_factory
from app.utils import create_upload_directories
from app.services import TaskQueue
from app.models.user import Base
from app.exceptions import AppException


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

    # Initialize ChromaDB
    try:
        from app.services.chroma_service import ChromaService
        ChromaService()
        print("ChromaDB initialized")
    except Exception as e:
        print(f"Warning: ChromaDB initialization failed: {e}")

    # Pre-load embedding model in background
    try:
        from app.services.embedding_service import EmbeddingService
        embedder = EmbeddingService()
        import asyncio as _asyncio
        _asyncio.create_task(_asyncio.to_thread(embedder._load_model))
    except Exception as e:
        print(f"Warning: Embedding model pre-load failed: {e}")

    # Recover orphaned pending KB documents from previous crashes
    try:
        from app.models.knowledge_base import KBDocument
        from sqlalchemy import select
        async with async_session_factory() as recovery_db:
            result = await recovery_db.execute(
                select(KBDocument).where(KBDocument.status == "pending")
            )
            pending_docs = result.scalars().all()
            if pending_docs:
                print(f"Found {len(pending_docs)} orphaned pending document(s), retrying...")
                from app.services.document_service import DocumentService
                for doc in pending_docs:
                    _asyncio.create_task(_retry_orphaned_doc(doc.id))
    except Exception as e:
        print(f"Warning: Startup KB doc recovery failed: {e}")

    yield

    # Shutdown - graceful shutdown with task completion wait
    print("Application shutting down...", flush=True)

    # Stop task queue gracefully (wait for active tasks)
    try:
        task_queue = TaskQueue()
        await task_queue.stop(wait=True, timeout=30.0)
    except Exception as e:
        print(f"Warning: Task queue shutdown error: {e}")

    # Cleanup YOLO service
    try:
        from app.services.yolo_service import YOLOService
        yolo = YOLOService()
        await yolo.cleanup()
    except Exception:
        pass

    await close_redis()
    await engine.dispose()
    print("Application shutdown complete", flush=True)


async def _retry_orphaned_doc(doc_id: int) -> None:
    """Retry processing an orphaned pending document with a small delay."""
    import asyncio as _asyncio
    await _asyncio.sleep(2)  # Let other startup tasks settle
    try:
        from app.services.document_service import DocumentService
        service = DocumentService()
        await service.process_document(doc_id)
        print(f"Orphaned doc {doc_id} recovered successfully")
    except Exception as e:
        print(f"Orphaned doc {doc_id} recovery failed: {e}")
        # Mark as failed so user knows
        try:
            async with async_session_factory() as db:
                from app.models.knowledge_base import KBDocument
                from sqlalchemy import select
                result = await db.execute(select(KBDocument).where(KBDocument.id == doc_id))
                doc = result.scalar_one_or_none()
                if doc and doc.status == "pending":
                    doc.status = "failed"
                    doc.error_message = f"服务重启恢复失败: {str(e)[:400]}"
                    await db.commit()
        except Exception:
            pass


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


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle application-level exceptions with proper error codes."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "data": None},
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
    from app.services.task_queue import TaskQueue
    task_queue = TaskQueue()
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "status": "healthy",
            "task_queue": {
                "running": task_queue._running,
                "active_tasks": len(task_queue._active_tasks),
                "max_workers": task_queue._max_workers,
            }
        }
    }


@app.get("/api/tasks/debug")
async def debug_tasks():
    """Debug endpoint to check pending tasks in DB."""
    from app.core.database import async_session_factory
    from app.models import DetectionRecord
    from sqlalchemy import select, func

    async with async_session_factory() as db:
        # Count by status
        result = await db.execute(
            select(DetectionRecord.status, func.count(DetectionRecord.id))
            .group_by(DetectionRecord.status)
        )
        status_counts = {row[0]: row[1] for row in result.all()}

        # Get recent pending tasks
        pending_result = await db.execute(
            select(DetectionRecord)
            .where(DetectionRecord.status == "pending")
            .order_by(DetectionRecord.created_at.desc())
            .limit(5)
        )
        pending_tasks = [
            {
                "id": r.id,
                "source_type": r.source_type,
                "mode": r.mode,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in pending_result.scalars().all()
        ]

        # Get recent failed tasks with error info
        failed_result = await db.execute(
            select(DetectionRecord)
            .where(DetectionRecord.status == "failed")
            .order_by(DetectionRecord.created_at.desc())
            .limit(5)
        )
        failed_tasks = [
            {
                "id": r.id,
                "source_type": r.source_type,
                "mode": r.mode,
                "source_path": r.source_path,
                "error": (r.result_json or {}).get("error", "unknown"),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in failed_result.scalars().all()
        ]

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "status_counts": status_counts,
            "pending_tasks": pending_tasks,
            "failed_tasks": failed_tasks,
        }
    }


from app.api.auth import router as auth_router
from app.api.llm_config import router as llm_config_router
from app.api.yolo_models import router as yolo_models_router
from app.api.detection import router as detection_router
from app.api.history import router as history_router
from app.api.system import router as system_router
from app.api.dashboard import router as dashboard_router
from app.api.tasks import router as tasks_router
from app.api.chat import router as chat_router
from app.api.knowledge_base import router as knowledge_base_router
from app.api.rag_chat import router as rag_chat_router
from app.api.embedding_config import router as embedding_config_router
from app.api.ocr_config import router as ocr_config_router

app.include_router(auth_router)
app.include_router(llm_config_router)
app.include_router(yolo_models_router)
app.include_router(detection_router)
app.include_router(history_router)
app.include_router(system_router)
app.include_router(dashboard_router)
app.include_router(tasks_router)

app.include_router(chat_router)
app.include_router(knowledge_base_router)
app.include_router(rag_chat_router)
app.include_router(embedding_config_router)
app.include_router(ocr_config_router)
