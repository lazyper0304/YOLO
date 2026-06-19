"""Background task queue service — dispatch only, processing delegated to Processors.

Supports parallel task processing with configurable concurrency.
Uses fire-and-forget pattern: the poll loop never blocks on running tasks.

Optimized with:
- ProcessPoolExecutor for CPU-intensive tasks
- ThreadPoolExecutor for I/O-intensive tasks
- Graceful shutdown with task completion等待
- Configurable concurrency via environment variables
"""

import asyncio
import logging
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from sqlalchemy import select

from app.core.database import async_session_factory
from app.config import settings
from app.models import DetectionRecord

logger = logging.getLogger(__name__)


class TaskQueue:
    """In-memory task queue with parallel background workers.

    Polls for pending DetectionRecords and spawns each as an independent
    background task. The poll loop never blocks — it just picks tasks and
    fires them off. A periodic cleanup loop removes finished tasks from
    the tracking set.

    Features:
    - ProcessPoolExecutor for CPU-intensive YOLO inference
    - ThreadPoolExecutor for I/O-bound operations
    - Graceful shutdown with configurable timeout
    - Configurable concurrency via settings
    """

    _instance: "TaskQueue | None" = None

    def __new__(cls, *args, **kwargs) -> "TaskQueue":
        if cls._instance is None:
            inst = super().__new__(cls)
            # Initialize all attributes here to avoid AttributeError
            inst._max_workers = kwargs.get("max_workers", settings.TASK_MAX_WORKERS)
            inst._task_timeout = kwargs.get("timeout", settings.TASK_TIMEOUT_SECONDS)
            inst._process_executor = ProcessPoolExecutor(
                max_workers=kwargs.get("process_workers", settings.PROCESS_POOL_MAX_WORKERS),
            )
            inst._thread_executor = ThreadPoolExecutor(
                max_workers=kwargs.get("thread_workers", settings.THREAD_POOL_MAX_WORKERS),
                thread_name_prefix="task-io"
            )
            inst._semaphore = asyncio.Semaphore(inst._max_workers)
            inst._running = False
            inst._active_tasks: dict[int, asyncio.Task] = {}
            inst._shutdown_event = asyncio.Event()
            inst._started = False
            cls._instance = inst

            print(f"[TaskQueue] Created: max_workers={inst._max_workers}, "
                  f"process_pool={settings.PROCESS_POOL_MAX_WORKERS}, "
                  f"thread_pool={settings.THREAD_POOL_MAX_WORKERS}", flush=True)
        return cls._instance

    @property
    def process_executor(self) -> ProcessPoolExecutor:
        """Expose process executor for CPU-intensive tasks (YOLO inference)."""
        return self._process_executor

    @property
    def thread_executor(self) -> ThreadPoolExecutor:
        """Expose thread executor for I/O-bound tasks."""
        return self._thread_executor

    async def start(self):
        """Start the task queue with background workers."""
        if self._started:
            logger.warning("TaskQueue already started")
            return

        self._running = True
        self._shutdown_event.clear()
        self._started = True

        print(f"[TaskQueue] Started (max_workers={self._max_workers}, "
              f"process_pool={settings.PROCESS_POOL_MAX_WORKERS}, "
              f"thread_pool={settings.THREAD_POOL_MAX_WORKERS})", flush=True)
        logger.info(
            "TaskQueue started (max_workers=%d, process_pool=%d, thread_pool=%d)",
            self._max_workers,
            settings.PROCESS_POOL_MAX_WORKERS,
            settings.THREAD_POOL_MAX_WORKERS,
        )
        asyncio.create_task(self._process_loop())
        asyncio.create_task(self._cleanup_loop())

    async def stop(self, wait: bool = True, timeout: float = 30.0):
        """Gracefully stop the task queue.

        Args:
            wait: If True, wait for active tasks to complete before stopping.
            timeout: Maximum time to wait for active tasks (seconds).
        """
        if not self._started:
            return

        print(f"[TaskQueue] Stopping (wait={wait}, timeout={timeout}s)...", flush=True)
        logger.info("Stopping TaskQueue (wait=%s, timeout=%.1fs)...", wait, timeout)
        self._running = False
        self._shutdown_event.set()

        if wait and self._active_tasks:
            active_count = len(self._active_tasks)
            print(f"[TaskQueue] Waiting for {active_count} active task(s)...", flush=True)
            logger.info("Waiting for %d active task(s) to complete...", active_count)

            try:
                # Wait for all active tasks with timeout
                done, pending = await asyncio.wait(
                    list(self._active_tasks.values()),
                    timeout=timeout,
                    return_when=asyncio.ALL_COMPLETED,
                )

                if pending:
                    print(f"[TaskQueue] Cancelling {len(pending)} task(s) that did not complete", flush=True)
                    logger.warning(
                        "Cancelling %d task(s) that did not complete within timeout",
                        len(pending),
                    )
                    for task in pending:
                        task.cancel()
                    # Wait briefly for cancellation to propagate
                    await asyncio.gather(*pending, return_exceptions=True)

                completed = len(done)
                print(f"[TaskQueue] Shutdown: {completed} completed, {len(pending) if pending else 0} cancelled", flush=True)
                logger.info("Shutdown: %d task(s) completed, %d cancelled",
                           completed, len(pending) if pending else 0)

            except Exception as e:
                print(f"[TaskQueue] Error during shutdown: {e}", flush=True)
                logger.error("Error during shutdown: %s", str(e))

        # Shutdown executors
        print("[TaskQueue] Shutting down thread/process pools...", flush=True)
        logger.info("Shutting down thread/process pools...")
        self._process_executor.shutdown(wait=True, cancel_futures=False)
        self._thread_executor.shutdown(wait=True, cancel_futures=False)

        self._active_tasks.clear()
        self._started = False
        print("[TaskQueue] Stopped", flush=True)
        logger.info("TaskQueue stopped")

    async def _process_loop(self):
        """Poll for pending tasks and dispatch each as a fire-and-forget task.

        The loop never blocks on processing. Each task is spawned independently
        and tracked in _active_tasks. The semaphore in _process_one limits
        concurrency.
        """
        print("[TaskQueue] Process loop started, polling for pending tasks...", flush=True)
        logger.info("[TaskQueue] Process loop started, polling for pending tasks...")

        while self._running:
            try:
                task_ids = []
                async with async_session_factory() as db:
                    result = await db.execute(
                        select(DetectionRecord)
                        .where(DetectionRecord.status == "pending")
                        .order_by(DetectionRecord.created_at.asc())
                        .limit(self._max_workers)
                        .with_for_update(skip_locked=True)
                    )
                    records = result.scalars().all()

                    if not records:
                        await db.commit()
                        await asyncio.sleep(1.0)  # Poll interval
                        continue

                    print(f"[TaskQueue] Found {len(records)} pending task(s): ids={[r.id for r in records]}", flush=True)
                    logger.info("Picked %d task(s): ids=%s", len(records), [r.id for r in records])
                    for record in records:
                        record.status = "running"
                        task_ids.append(record.id)
                    await db.commit()

                # Fire-and-forget: spawn each task independently, never block
                for tid in task_ids:
                    print(f"[TaskQueue] Spawning task {tid}", flush=True)
                    task = asyncio.create_task(self._process_one(tid))
                    self._active_tasks[tid] = task
                    task.add_done_callback(lambda t, tid=tid: self._on_task_done(tid, t))

            except Exception as e:
                if self._running:  # Only log if not shutting down
                    print(f"[TaskQueue] Error in process loop: {e}", flush=True)
                    logger.error("Task queue error: %s", str(e), exc_info=True)
                    await asyncio.sleep(2)

    def _on_task_done(self, task_id: int, task: asyncio.Task):
        """Callback when a task completes (success or failure)."""
        self._active_tasks.pop(task_id, None)

        if task.cancelled():
            print(f"[TaskQueue] Task {task_id} was cancelled", flush=True)
            logger.info("Task %d was cancelled", task_id)
        elif task.exception():
            print(f"[TaskQueue] Task {task_id} failed: {task.exception()}", flush=True)
            logger.error("Task %d failed with exception: %s", task_id, task.exception())
        else:
            print(f"[TaskQueue] Task {task_id} completed successfully", flush=True)
            logger.debug("Task %d completed successfully", task_id)

    async def _cleanup_loop(self):
        """Periodically log active task count and health status."""
        while self._running:
            try:
                await asyncio.sleep(30)
                active = len(self._active_tasks)
                sem_avail = self._semaphore._value
                if active > 0 or sem_avail < self._max_workers:
                    logger.info(
                        "Health: active_tasks=%d, semaphore=%d/%d, "
                        "process_pool_active=%d, thread_pool_active=%d",
                        active, sem_avail, self._max_workers,
                        len(self._process_executor._threads),
                        len(self._thread_executor._threads),
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _process_one(self, task_id: int):
        """Acquire semaphore and run a single task (no timeout — runs until completion or cancellation)."""
        async with self._semaphore:
            try:
                await self._execute(task_id)
            except asyncio.CancelledError:
                print(f"[TaskQueue] Task {task_id} cancelled during execution", flush=True)
                logger.info("Task %d cancelled during execution", task_id)
                raise

    async def _execute(self, task_id: int):
        """Resolve processor and process task within a DB session."""
        print(f"[TaskQueue] Executing task {task_id}...", flush=True)
        async with async_session_factory() as proc_db:
            fresh_record: DetectionRecord | None = None
            try:
                fresh = await proc_db.execute(
                    select(DetectionRecord).where(DetectionRecord.id == task_id)
                )
                fresh_record = fresh.scalar_one_or_none()
                if fresh_record is None:
                    print(f"[TaskQueue] Task {task_id} not found in DB", flush=True)
                    return

                print(f"[TaskQueue] Task {task_id}: source_type={fresh_record.source_type}, mode={fresh_record.mode}, model_id={fresh_record.yolo_model_id}", flush=True)
                processor = self._resolve_processor(fresh_record, proc_db)
                print(f"[TaskQueue] Task {task_id}: Using processor {type(processor).__name__}", flush=True)
                logger.info("Processing task %d via %s", task_id, type(processor).__name__)

                await processor.process(fresh_record)
                await proc_db.commit()

                print(f"[TaskQueue] Task {task_id} completed successfully", flush=True)
                logger.info("Task %d completed", task_id)

            except asyncio.CancelledError:
                print(f"[TaskQueue] Task {task_id} cancelled", flush=True)
                # Re-raise to allow proper cancellation handling
                raise
            except Exception as e:
                print(f"[TaskQueue] Task {task_id} failed with error: {e}", flush=True)
                if fresh_record is not None:
                    fresh_record.result_json = {"error": str(e)}
                    fresh_record.status = "failed"
                    await proc_db.commit()
                logger.error("Task %d failed: %s", task_id, str(e), exc_info=True)

    async def _mark_task_failed(self, task_id: int, error_message: str):
        """Mark a task as failed with error message."""
        try:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(DetectionRecord).where(DetectionRecord.id == task_id)
                )
                record = result.scalar_one_or_none()
                if record and record.status in ("running", "pending"):
                    record.result_json = {"error": error_message}
                    record.status = "failed"
                    await db.commit()
                    print(f"[TaskQueue] Marked task {task_id} as failed: {error_message}", flush=True)
                    logger.info("Marked task %d as failed: %s", task_id, error_message)
        except Exception as e:
            print(f"[TaskQueue] Failed to mark task {task_id} as failed: {e}", flush=True)
            logger.error("Failed to mark task %d as failed: %s", task_id, str(e))

    def _resolve_processor(self, record: DetectionRecord, db):
        """Return the appropriate processor for the given task record."""
        if record.source_type == "camera":
            from app.services.processors import CameraIPProcessor, CameraWebcamProcessor
            if record.source_path and record.source_path.startswith(("rtsp://", "http://")):
                return CameraIPProcessor(db, running_check=lambda: self._running)
            return CameraWebcamProcessor(db)

        if record.source_type == "video":
            if not os.path.exists(record.source_path):
                raise FileNotFoundError(f"Source not found: {record.source_path}")
            if record.mode in ("llm_only", "collaborative"):
                from app.services.processors import FrameAnalysisProcessor
                return FrameAnalysisProcessor(db)
            from app.services.processors import VideoProcessor
            return VideoProcessor(db)

        # Image / default
        if not os.path.exists(record.source_path):
            raise FileNotFoundError(f"Source not found: {record.source_path}")
        from app.services.processors import ImageProcessor
        return ImageProcessor(db)
