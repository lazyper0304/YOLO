# YOLO 检测平台模块化重构方案

## 一、概述

### 1.1 重构目标

本次重构是**纯代码组织层面的改进**，不改动任何 API 接口签名、数据库 Schema 或业务行为。目标：

1. **导入路径简洁化** — 通过 `__init__.py` 重导出，将深层导入缩短为包级导入
2. **关注点分离** — 路由层只做参数校验和响应构造，业务逻辑全部下沉到 Service 层
3. **职责单一化** — 拆分巨型模块（`task_queue.py`、`config.py`），每个模块只做一件事
4. **消除重复** — 统一响应格式、统一异常处理、统一布局组件

### 1.2 重构原则

| 原则 | 说明 |
|------|------|
| **增量改造** | 每次只改一个模块，改完验证后再改下一个 |
| **向后兼容** | 保留旧导入路径的兼容性重导出，不破坏现有引用 |
| **API 不变** | 不修改任何 REST 端点路径、请求/响应格式 |
| **测试先行** | 每完成一个任务立即验证所有端点仍正常响应 |
| **可回滚** | 每个任务独立可回滚，通过 git revert 即可 |

---

## 二、后端重构任务列表

### 2.1 现状诊断

#### 问题 1：`__init__.py` 几乎全空

6 个包目录中，仅 `models/__init__.py` 做了重导出；其余 5 个（`api/`、`core/`、`services/`、`schemas/`、`utils/`）仅有空文档字符串。导致导入冗长：

```python
# 现状（冗长）
from app.services.detection_service import DetectionService
from app.api.deps import get_current_user
from app.core.database import get_db

# 目标（简洁）
from app.services import DetectionService
from app.api import get_current_user
from app.core import get_db
```

#### 问题 2：路由层混入业务逻辑

以下 4 个路由文件在端点函数中直接写 ORM 查询：

| 文件 | 行数 | 问题 |
|------|------|------|
| `api/dashboard.py` | 60 | 直接在路由中查询 User/YOLOModel/LLMConfig/DetectionRecord |
| `api/history.py` | ~80 | 直接在路由中执行复杂查询和分页逻辑 |
| `api/llm_config.py` | ~100 | LLM 配置 CRUD 的 ORM 操作写在路由中 |
| `api/tasks.py` | ~90 | 任务列表查询、状态更新直接在路由中操作 DB |

#### 问题 3：`task_queue.py` 过于庞大

579 行，混合了：
- 任务队列调度循环（`_process_loop`）
- 图片处理（`_process_image`）
- 视频逐帧 YOLO 处理（`_process_video`，97 行）
- 视频逐帧 LLM 分析（`_process_video_with_llm`，199 行）
- 摄像头 IP 处理（`_process_camera_ip`，150 行）
- 摄像头 Webcam 占位（`_process_camera_webcam`）

#### 问题 4：死代码

`utils/image_utils.py`（37 行）提供 `validate_image`、`get_image_dimensions`、`resize_image`、`image_to_base64`，功能与 `services/image_service.py` 重复，且经搜索确认**无任何代码引用**。

#### 问题 5：配置单文件

`config.py`（100 行）的 `Settings` 类混合了数据库、Redis、JWT、上传、YOLO、LLM、Server 共 7 个领域的配置。

#### 问题 6：无统一响应辅助

每个端点手动构造响应：
```python
return {"code": 0, "message": "ok", "data": {...}}
```

#### 问题 7：无异常层次

仅使用原始的 `HTTPException`，没有自定义异常类。

### 2.2 任务表

| 编号 | 任务 | 涉及文件 | 优先级 | 依赖 |
|------|------|---------|--------|------|
| **B01** | 规范化 `__init__.py`（全包重导出） | `api/__init__.py`、`core/__init__.py`、`services/__init__.py`、`schemas/__init__.py`、`utils/__init__.py`、以及所有引用这些包的 `.py` 文件（约 25 个） | P0 | — |
| **B02** | 创建异常体系 + 统一响应工具 | **新建** `app/exceptions.py`、`app/api/responses.py`；**修改** `main.py`（全局异常处理器）、所有 9 个路由文件（替换手动响应构造） | P0 | — |
| **B03** | 拆分 `config.py` 为领域子模块 | **新建** `app/config/` 包（7 个子模块 + `__init__.py`）；**修改** `config.py` 改为兼容性重导出；**修改** 所有引用 `app.config` 的文件（约 12 个） | P1 | B01 |
| **B04** | 从路由层抽取业务逻辑到 Service 层 | **新建** `services/dashboard_service.py`、`services/history_service.py`、`services/llm_config_service.py`；**修改** `api/dashboard.py`、`api/history.py`、`api/llm_config.py`、`api/tasks.py` | P1 | B01 |
| **B05** | 拆分 `task_queue.py` + 移除死代码 | **新建** `services/processors/` 包（`__init__.py`、`video_processor.py`、`frame_analysis_processor.py`、`camera_processor.py`）；**修改** `task_queue.py`（仅保留调度循环）；**删除** `utils/image_utils.py` | P1 | B01 |
| **B06** | Service 层抽象基类 + 包重组 | **新建** `services/base.py`；**修改** 所有 7 个 service 文件继承基类；可选：按领域重组为 `services/detection/`、`services/auth/` 等子包 | P2 | B04, B05 |

### 2.3 各任务详细说明

#### B01：规范化 `__init__.py`

**目标**：所有包级 `__init__.py` 提供 `__all__` 和主要符号重导出。

**具体改动**：

```python
# app/api/__init__.py
"""API routers package."""
from app.api.deps import get_current_user
from app.api.auth import router as auth_router
from app.api.detection import router as detection_router
# ... 其余 router

__all__ = ["get_current_user", "auth_router", "detection_router", ...]
```

```python
# app/core/__init__.py
"""Core infrastructure."""
from app.core.database import engine, get_db, async_session_factory
from app.core.redis_client import init_redis, close_redis, get_redis
from app.core.security import hash_password, verify_password, create_token, decrypt_api_key

__all__ = ["engine", "get_db", "async_session_factory", "init_redis", "close_redis", ...]
```

```python
# app/services/__init__.py
"""Service layer."""
from app.services.auth_service import AuthService
from app.services.detection_service import DetectionService
from app.services.image_service import ImageService
from app.services.llm_service import LLMService
from app.services.yolo_service import YOLOService
from app.services.video_service import VideoService
from app.services.task_queue import TaskQueue

__all__ = ["AuthService", "DetectionService", "ImageService", "LLMService", "YOLOService", "VideoService", "TaskQueue"]
```

```python
# app/schemas/__init__.py
"""Pydantic schemas."""
from app.schemas.auth import *
from app.schemas.detection import *
from app.schemas.history import *
from app.schemas.llm_config import *
from app.schemas.yolo_model import *

__all__ = [...]  # 汇总所有
```

**随后更新所有 `.py` 文件中的导入语句**（约 25 个文件），将深层导入替换为包级导入。示例：

```python
# Before
from app.services.detection_service import DetectionService
from app.core.database import engine, get_db
# After
from app.services import DetectionService
from app.core import engine, get_db
```

**为什么先做**：这是影响面最大但风险最低的改动。导入路径变更不改变任何逻辑，确保后续所有任务都在简洁的导入基础上进行。

---

#### B02：创建异常体系 + 统一响应工具

**目标**：建立分层异常体系和统一响应格式，消除每个端点手动构造 `{"code": ..., "message": ..., "data": ...}` 的重复模式。

**新建 `app/exceptions.py`**：

```python
"""Custom exception hierarchy for the application."""

class AppException(Exception):
    """Base application exception."""
    def __init__(self, message: str, code: int = 1, status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class NotFoundException(AppException):
    """Resource not found."""
    def __init__(self, message: str = "资源不存在", code: int = 404):
        super().__init__(message, code=code, status_code=404)


class ValidationException(AppException):
    """Validation error."""
    def __init__(self, message: str = "参数验证失败", code: int = 422):
        super().__init__(message, code=code, status_code=422)


class AuthException(AppException):
    """Authentication/authorization error."""
    def __init__(self, message: str = "认证失败", code: int = 401):
        super().__init__(message, code=code, status_code=401)


class BusinessException(AppException):
    """Business logic error."""
    def __init__(self, message: str, code: int = 1):
        super().__init__(message, code=code, status_code=400)


class ServiceUnavailableException(AppException):
    """External service unavailable (YOLO model load fail, Redis down, etc.)."""
    def __init__(self, message: str = "服务暂不可用", code: int = 503):
        super().__init__(message, code=code, status_code=503)
```

**新建 `app/api/responses.py`**：

```python
"""Unified API response helpers."""
from typing import Any

def success_response(data: Any = None, message: str = "ok") -> dict:
    """Standard success response."""
    return {"code": 0, "message": message, "data": data}


def paginated_response(
    items: list[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Standard paginated response."""
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


def error_response(code: int, message: str, data: Any = None) -> dict:
    """Standard error response."""
    return {"code": code, "message": message, "data": data}
```

**修改 `main.py` 全局异常处理器**：

```python
from app.exceptions import AppException

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "data": None},
    )
```

**修改路由文件**，将手动响应构造替换为辅助函数 + 异常抛出：

```python
# Before (dashboard.py)
return {"code": 0, "message": "ok", "data": {...}}

# After
from app.api.responses import success_response
return success_response(data={...})

# 错误场景 Before
raise HTTPException(status_code=404, detail="模型不存在")

# After
from app.exceptions import NotFoundException
raise NotFoundException("模型不存在")
```

**影响面**：9 个路由文件 + `main.py`。这是所有后续 Service 层抽取的前置基础。

---

#### B03：拆分配置为领域子模块

**目标**：将 100 行的单体 `config.py` 拆分为 7 个领域子模块。

**新目录结构**：

```
app/config/
├── __init__.py          # 汇总导出所有子配置，提供统一的 settings 实例
├── database.py          # MYSQL_HOST/PORT/USER/PASSWORD/DATABASE, DATABASE_URL
├── redis.py             # REDIS_HOST/PORT/PASSWORD/DB
├── auth.py              # SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRATION_HOURS
├── upload.py            # UPLOAD_DIR, MAX_IMAGE/VIDEO/MODEL_SIZE_MB, size byte properties
├── yolo.py              # YOLO_DEFAULT_MODEL, CONFIDENCE_THRESHOLD, DEVICE, MODELS_DIR
├── llm.py               # LLM_TIMEOUT_SECONDS, LLM_MAX_RETRIES
├── server.py            # BACKEND_HOST/PORT, CORS_ORIGINS, ENVIRONMENT, temp_dir
```

**`app/config/__init__.py`** 汇总所有子 Settings 到一个统一的 `settings` 实例：

```python
"""Application configuration."""
from app.config.database import DatabaseSettings
from app.config.redis import RedisSettings
from app.config.auth import AuthSettings
from app.config.upload import UploadSettings
from app.config.yolo import YOLOSettings
from app.config.llm import LLMSettings
from app.config.server import ServerSettings

class Settings(DatabaseSettings, RedisSettings, AuthSettings, UploadSettings, YOLOSettings, LLMSettings, ServerSettings):
    """Unified application settings."""
    pass

settings = Settings()
```

**保留旧 `config.py`** 为兼容性重导出（避免一次性修改所有引用文件）：

```python
# config.py (兼容性桩)
"""DEPRECATED: Import from app.config instead. Kept for backward compatibility."""
from app.config import settings  # noqa
```

**随后逐步迁移所有 `from app.config import settings` → `from app.config import settings`**（路径不变，因为 `app/config/__init__.py` 也导出 `settings`，实际导入路径仍然是 `app.config` → `settings`，所以无需修改任何引用文件）。

**风险**：使用多重继承合并 Settings 类，需确保无属性名冲突。当前各领域字段前缀各异（`MYSQL_`、`REDIS_`、`YOLO_` 等），无冲突风险。

---

#### B04：从路由层抽取业务逻辑

**目标**：将 `dashboard.py`、`history.py`、`llm_config.py`、`tasks.py` 中的 ORM 操作抽取到对应的 Service 类。

**新建 Service 文件**：

| 新文件 | 职责 | 来源 |
|--------|------|------|
| `services/dashboard_service.py` | `DashboardService.get_stats(user_id, db)` | 从 `api/dashboard.py` 抽取 |
| `services/history_service.py` | `HistoryService.list_records()`, `get_record()`, `delete_record()` | 从 `api/history.py` 抽取 |
| `services/llm_config_service.py` | `LLMConfigService.create()`, `list()`, `update()`, `delete()`, `test()` | 从 `api/llm_config.py` 抽取 |

**改造前（示例 `dashboard.py`）**：

```python
@router.get("/stats")
async def dashboard_stats(current_user=Depends(get_current_user), db=Depends(get_db)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total_result = await db.execute(select(func.count(DetectionRecord.id)).where(...))
    # ... 30+ 行 ORM 查询
    return {"code": 0, "message": "ok", "data": {...}}
```

**改造后**：

```python
# services/dashboard_service.py
class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_stats(self, user_id: int) -> dict:
        """Return dashboard statistics for the given user."""
        # 原路由中的 ORM 查询逻辑移到这里
        ...

# api/dashboard.py
from app.services import DashboardService
from app.api.responses import success_response

@router.get("/stats")
async def dashboard_stats(current_user=Depends(get_current_user), db=Depends(get_db)):
    service = DashboardService(db)
    stats = await service.get_stats(current_user.id)
    return success_response(data=stats)
```

**注意**：`llm_config.py` 的 CRUD 本身就是配置管理操作，`LLMConfigService` 应该是一个标准的 CRUD Service，类似于已有的 `AuthService` 模式。

---

#### B05：拆分 `task_queue.py` + 移除死代码

**目标**：将 579 行的巨型文件拆分为调度器 + 3 个处理器。

**新目录结构**：

```
app/services/
├── task_queue.py           # 保留：TaskQueue 调度器（~100行，仅 _process_loop + 路由分发）
├── processors/
│   ├── __init__.py
│   ├── image_processor.py      # _process_image（从 task_queue.py 移出）
│   ├── video_processor.py      # _process_video（从 task_queue.py 移出）
│   ├── frame_analysis_processor.py  # _process_video_with_llm（从 task_queue.py 移出）
│   └── camera_processor.py     # _process_camera_ip + _process_camera_webcam（从 task_queue.py 移出）
```

**`task_queue.py` 拆分后**（仅保留调度循环）：

```python
class TaskQueue:
    # ... 单例模式 + start/stop 保留不变

    async def _process_loop(self):
        """Poll for pending tasks and dispatch to appropriate processor."""
        # 仅保留：poll pending → 获取锁 → 根据 source_type/mode 路由到处理器
        # 不包含任何具体的处理逻辑

    async def _dispatch(self, db, record):
        """Route task to the correct processor."""
        if record.source_type == "video":
            if record.mode in ("llm_only", "collaborative"):
                from app.services.processors.frame_analysis_processor import FrameAnalysisProcessor
                processor = FrameAnalysisProcessor(db)
                await processor.process(record)
            else:
                from app.services.processors.video_processor import VideoProcessor
                processor = VideoProcessor(db)
                await processor.process(record)
        else:
            from app.services.processors.image_processor import ImageProcessor
            processor = ImageProcessor(db)
            await processor.process(record)
```

**删除死代码**：

```bash
rm backend/app/utils/image_utils.py
```

确认为死代码的证据：`grep -r "image_utils" backend/app/` 仅返回 `from app.utils.image_utils import ...` 自身定义。`services/image_service.py` 提供了完全重复的功能且已被 `detection_service.py` 引用。

---

#### B06：Service 层抽象基类（P2）

**目标**：为所有 Service 提供统一的 `BaseService` 抽象基类。

```python
# app/services/base.py
from abc import ABC
from sqlalchemy.ext.asyncio import AsyncSession

class BaseService(ABC):
    """Abstract base for all service classes."""

    def __init__(self, db: AsyncSession):
        self.db = db
```

所有 Service 类改为 `class AuthService(BaseService):`，构造函数统一为 `super().__init__(db)`。这一改动极轻量，但为未来扩展（如统一日志、统一事务管理）奠定基础。

可选：将 services 按领域重组为子包：
```
app/services/
├── base.py
├── auth/          # auth_service.py
├── detection/     # detection_service.py, yolo_service.py, image_service.py
├── task/          # task_queue.py, processors/
├── llm/           # llm_service.py, llm_config_service.py
├── history/       # history_service.py
└── dashboard/     # dashboard_service.py
```

这个子包重组放在 P2，且标注为"可选"，因为其收益（领域更清晰）与成本（大量导入路径变更）需要团队评估。

---

## 三、前端重构任务列表

### 3.1 现状诊断

#### 问题 1：Tasks API 未封装

3 个视图直接使用 `client.get/post/delete('/api/tasks/...')`：

| 文件 | 裸 API 调用数 |
|------|--------------|
| `DetectionView.vue` | 7 处（get tasks, post task, get task, delete task, batch-delete, pause, resume） |
| `VideoSourceView.vue` | 4 处（post realtime, get tasks, post task, delete task, get task） |
| `ChatView.vue` | 1 处（get tasks） |

#### 问题 2：无 Task Store

任务列表、详情、操作状态散落在多个 view 的本地 `ref` 中，无统一状态管理。

#### 问题 3：Dashboard/System API 未封装

- `DashboardView.vue`：直接用 `client.get('/api/dashboard/stats')`
- `AppHeader.vue`：直接用 `client.get('/api/system/status')`

#### 问题 4：布局模板重复

6 个视图各自写了相同的布局结构：
```html
<div class="h-screen flex flex-col overflow-hidden">
  <AppHeader />
  <div class="flex-1 grid grid-cols-[180px_1fr] overflow-hidden">
    <LeftSidebar />
    <main class="flex-1 overflow-auto bg-gray-50">
      <!-- 页面内容 -->
    </main>
  </div>
</div>
```

#### 问题 5：组件目录无 barrel export

`components/chat/`、`components/common/`、`components/config/`、`components/detection/`、`components/layout/` 均无 `index.ts` 统一导出。

### 3.2 任务表

| 编号 | 任务 | 涉及文件 | 优先级 | 依赖 |
|------|------|---------|--------|------|
| **F01** | 封装缺失的 API 模块 + 创建 Task Store | **新建** `api/tasks.ts`、`api/dashboard.ts`、`api/system.ts`、`stores/task.ts`；**修改** `DetectionView.vue`、`VideoSourceView.vue`、`ChatView.vue`、`DashboardView.vue`、`AppHeader.vue` | P0 | — |
| **F02** | 创建 barrel exports | **新建** `components/index.ts`、`components/chat/index.ts`、`components/common/index.ts`、`components/config/index.ts`、`components/detection/index.ts`、`components/layout/index.ts`、`composables/index.ts` | P1 | — |
| **F03** | 抽取 LayoutShell 组件 | **新建** `components/layout/LayoutShell.vue`；**修改** 6 个视图文件：`DashboardView.vue`、`DetectionView.vue`、`HistoryView.vue`、`ModelsView.vue`、`ChatView.vue`、`VideoSourceView.vue` | P1 | F02 |
| **F04** | 视图业务逻辑抽取为 composables | **新建** `composables/useTaskList.ts`、`composables/useChat.ts`；**修改** `DetectionView.vue`、`ChatView.vue`、`VideoSourceView.vue` | P2 | F01 |

### 3.3 各任务详细说明

#### F01：封装 API 模块 + Task Store

**新建 `api/tasks.ts`**：

```typescript
import client from './client'

export interface Task {
  id: number
  mode: string
  source_type: string
  status: string
  progress: number
  result_json: any
  created_at: string
  // ...
}

export async function fetchTasks(params?: { page?: number; page_size?: number; status?: string }) {
  const res = await client.get('/api/tasks', { params })
  return res.data.data
}

export async function getTask(id: number) {
  const res = await client.get(`/api/tasks/${id}`)
  return res.data.data
}

export async function createTask(form: FormData) {
  const res = await client.post('/api/tasks', form)
  return res.data.data
}

export async function deleteTask(id: number) {
  await client.delete(`/api/tasks/${id}`)
}

export async function batchDeleteTasks(ids: number[]) {
  await client.post('/api/tasks/batch-delete', ids)
}

export async function pauseTask(id: number) {
  await client.post(`/api/tasks/${id}/pause`)
}

export async function resumeTask(id: number) {
  await client.post(`/api/tasks/${id}/resume`)
}
```

**新建 `api/dashboard.ts`**：

```typescript
import client from './client'
import type { DashboardData } from '@/types/api'

export async function fetchDashboardStats(): Promise<DashboardData> {
  const res = await client.get('/api/dashboard/stats')
  return res.data.data
}
```

**新建 `api/system.ts`**：

```typescript
import client from './client'

export async function getSystemStatus() {
  const res = await client.get('/api/system/status')
  return res.data.data
}
```

**新建 `stores/task.ts`**：

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchTasks, getTask, createTask, deleteTask, pauseTask, resumeTask, type Task } from '@/api/tasks'

export const useTaskStore = defineStore('task', () => {
  const tasks = ref<Task[]>([])
  const currentTask = ref<Task | null>(null)
  const loading = ref(false)

  async function loadTasks(params?: Record<string, any>) {
    loading.value = true
    try {
      const data = await fetchTasks(params)
      tasks.value = data.items ?? data
    } finally {
      loading.value = false
    }
  }

  async function loadTask(id: number) {
    currentTask.value = await getTask(id)
    return currentTask.value
  }

  async function submitTask(form: FormData) {
    const task = await createTask(form)
    tasks.value.unshift(task)
    return task
  }

  async function removeTask(id: number) {
    await deleteTask(id)
    tasks.value = tasks.value.filter(t => t.id !== id)
  }

  async function togglePause(id: number) {
    const task = tasks.value.find(t => t.id === id)
    if (!task) return
    if (task.status === 'running') {
      await pauseTask(id)
    } else {
      await resumeTask(id)
    }
    await loadTasks()
  }

  return { tasks, currentTask, loading, loadTasks, loadTask, submitTask, removeTask, togglePause }
})
```

**修改视图文件**：将裸 `client.get/post/delete` 调用替换为 API 模块函数或 Store actions。例如 `DetectionView.vue`：

```typescript
// Before
const res = await client.get('/api/tasks', { params: { page_size: 50 } })

// After
import { useTaskStore } from '@/stores/task'
const taskStore = useTaskStore()
await taskStore.loadTasks({ page_size: 50 })
```

---

#### F02：创建 Barrel Exports

**`components/chat/index.ts`**：

```typescript
export { default as MarkdownRenderer } from './MarkdownRenderer.vue'
```

**`components/common/index.ts`**：

```typescript
export { default as FileUploader } from './FileUploader.vue'
export { default as LoadingOverlay } from './LoadingOverlay.vue'
```

**`components/detection/index.ts`**：

```typescript
export { default as BBoxList } from './BBoxList.vue'
export { default as ImageCanvas } from './ImageCanvas.vue'
export { default as LLMAnalysis } from './LLMAnalysis.vue'
export { default as ModeSelector } from './ModeSelector.vue'
export { default as ModelSelector } from './ModelSelector.vue'
```

**`components/config/index.ts`**：

```typescript
export { default as LLMConfigDialog } from './LLMConfigDialog.vue'
export { default as YOLOModelUpload } from './YOLOModelUpload.vue'
```

**`components/layout/index.ts`**：

```typescript
export { default as AppHeader } from './AppHeader.vue'
export { default as LeftSidebar } from './LeftSidebar.vue'
export { default as RightPanel } from './RightPanel.vue'
```

**`components/index.ts`**（顶层聚合）：

```typescript
export * from './chat'
export * from './common'
export * from './config'
export * from './detection'
export * from './layout'
```

**`composables/index.ts`**：

```typescript
export { useCamera } from './useCamera'
export { useFileUpload } from './useFileUpload'
```

**收益**：视图文件中的导入可以从 5 行缩减为 1 行：
```typescript
// Before
import AppHeader from '@/components/layout/AppHeader.vue'
import LeftSidebar from '@/components/layout/LeftSidebar.vue'
import BBoxList from '@/components/detection/BBoxList.vue'
// After
import { AppHeader, LeftSidebar, BBoxList } from '@/components'
```

---

#### F03：抽取 LayoutShell 组件

**新建 `components/layout/LayoutShell.vue`**：

```vue
<template>
  <div class="h-screen flex flex-col overflow-hidden">
    <AppHeader />
    <div class="flex-1 grid grid-cols-[180px_1fr] overflow-hidden">
      <LeftSidebar />
      <main class="flex-1 overflow-auto bg-gray-50">
        <slot />
      </main>
      <slot name="right-panel" />
    </div>
  </div>
</template>

<script setup lang="ts">
import AppHeader from './AppHeader.vue'
import LeftSidebar from './LeftSidebar.vue'
</script>
```

**修改 6 个视图**：

```vue
<!-- Before: 每个 view 重复布局结构 -->
<div class="h-screen flex flex-col overflow-hidden">
  <AppHeader />
  <div class="flex-1 grid grid-cols-[180px_1fr] overflow-hidden">
    <LeftSidebar />
    <main class="flex-1 overflow-auto bg-gray-50">
      <!-- 页面内容 -->
    </main>
  </div>
</div>

<!-- After: 使用 LayoutShell -->
<template>
  <LayoutShell>
    <!-- 页面内容 -->
    <template v-if="showRightPanel" #right-panel>
      <RightPanel />
    </template>
  </LayoutShell>
</template>
```

**收益**：消除 6 × 7 行 = 42 行重复模板代码，未来新增页面只需包裹 `<LayoutShell>` 即可。

---

#### F04：视图业务逻辑抽取为 Composables（P2）

**目标**：将 DetectionView、ChatView、VideoSourceView 中的复杂业务逻辑抽取为可测试的 composable 函数。

**`composables/useTaskList.ts`**：

```typescript
import { computed } from 'vue'
import { useTaskStore } from '@/stores/task'

export function useTaskList() {
  const store = useTaskStore()
  // 提取 DetectionView + VideoSourceView 共用的任务列表轮询、筛选、选择逻辑
  const runningTasks = computed(() => store.tasks.filter(t => t.status === 'running'))
  // ...
  return { ...store, runningTasks }
}
```

**`composables/useChat.ts`**：

```typescript
export function useChat() {
  // 提取 ChatView 中的消息发送、SSE 连接、历史加载等逻辑
}
```

---

## 四、共享约定

### 4.1 Python 后端约定

```python
# === 导入规范 ===
# 优先使用包级导入
from app.services import DetectionService  # ✅ 推荐
from app.services.detection_service import DetectionService  # ⚠️ 可接受（兼容期）

# === 响应构造 ===
# 始终使用统一响应辅助函数
from app.api.responses import success_response, error_response, paginated_response
return success_response(data=result)  # ✅
return {"code": 0, "message": "ok", "data": result}  # ❌ 不再使用

# === 异常处理 ===
# 抛出 AppException 子类，由全局异常处理器统一捕获
from app.exceptions import NotFoundException, ValidationException
raise NotFoundException("YOLO模型不存在")  # ✅
raise HTTPException(status_code=404, detail="...")  # ❌ 不再使用

# === Service 层 ===
# 所有 Service 接受 db: AsyncSession 作为构造参数
# 所有 Service 方法为 async
class FooService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def do_something(self, ...) -> ...:
        ...

# === 路由层 ===
# 路由函数只做：参数校验 → 调用 Service → 返回响应
# 不包含任何 ORM 操作
@router.get("/items")
async def list_items(db=Depends(get_db), user=Depends(get_current_user)):
    service = ItemService(db)
    items = await service.list_by_user(user.id)
    return success_response(data=items)
```

### 4.2 TypeScript 前端约定

```typescript
// === API 调用 ===
// 始终通过 api/ 模块调用，不在视图中直接使用 client
import { fetchTasks, createTask } from '@/api/tasks'  // ✅
client.get('/api/tasks')  // ❌ 禁止在视图中使用

// === 组件导入 ===
// 优先使用 barrel export
import { AppHeader, BBoxList } from '@/components'  // ✅ 推荐
import AppHeader from '@/components/layout/AppHeader.vue'  // ⚠️ 可接受

// === 状态管理 ===
// 跨视图共享的状态放 Pinia store
// 视图本地状态用 composable + ref
// 避免在 .vue <script setup> 中写超过 50 行业务逻辑

// === 布局 ===
// 所有需要标准布局的视图使用 LayoutShell
<LayoutShell>...</LayoutShell>  // ✅
```

### 4.3 通用约定

- **API 响应格式**：`{ code: 0, message: "ok", data: ... }` — 成功 code=0，业务错误 code>0
- **认证**：JWT Bearer Token，存储在 `localStorage.access_token`
- **日期格式**：ISO 8601 UTC（后端 `datetime.now(timezone.utc)`）
- **分页参数**：`page`（从1开始）、`page_size`（默认20）
- **Git 提交粒度**：每个任务一个独立 commit，commit message 格式 `[B01]` 或 `[F03]` 前缀

---

## 五、实现顺序

按依赖关系和风险从低到高排列：

```
阶段一：基础设施（无业务影响，可独立验证）
├── B01  规范化 __init__.py（导入路径变更）
├── B02  异常体系 + 统一响应（新建文件，不影响现有行为）
│
阶段二：后端模块拆分（每个模块独立）
├── B03  配置拆分（新建子模块，保留兼容层）
├── B04  路由层业务逻辑抽取 → Service（Dashboard → History → LLMConfig → Tasks，按此顺序逐个改）
├── B05  拆分 task_queue + 删除 image_utils
│
阶段三：前端模块化（独立于后端）
├── F01  API 封装 + Task Store
├── F02  Barrel exports
├── F03  LayoutShell 抽取
│
阶段四：优化收尾（可选，低优先级）
├── B06  Service 抽象基类
├── F04  视图 composables 抽取
```

**依赖关系图**：

```
B01 ──→ B03 ──→ B04 ──→ B05 ──→ B06
 │                                   
 └──→ B02                            

F01 ──→ F02 ──→ F03
 │         │
 └──→ F04 ←┘
```

**建议执行节奏**：

| 轮次 | 任务 | 预计耗时 | 风险等级 |
|------|------|---------|---------|
| 第1轮 | B01 | 1h | 低（纯导入变更） |
| 第2轮 | B02 | 1.5h | 低（新建文件+逐步替换） |
| 第3轮 | B03 | 1h | 低（保留兼容层） |
| 第4轮 | B04 | 2h | 中（涉及路由逻辑迁移，需逐个验证） |
| 第5轮 | B05 | 1.5h | 中（task_queue 拆分，需验证异步任务） |
| 第6轮 | F01 | 1.5h | 低（新建 API 模块 + Store） |
| 第7轮 | F02 + F03 | 1.5h | 低（barrel + 模板抽取） |
| 第8轮 | B06 + F04 | 1h | 低（可选优化） |

---

## 六、风险与回滚策略

### 6.1 风险矩阵

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| `__init__.py` 重导出导致循环导入 | 高（服务启动失败） | 低 | B01 改造时逐个包验证 `python -c "from app.xxx import ..."`；出现循环导入时通过延迟导入（函数内 import）解决 |
| 配置拆分后属性缺失 | 高（运行时 AttributeError） | 低 | B03 使用多重继承 + 保留原 config.py 兼容层；运行 `python -c "from app.config import settings; print(dir(settings))"` 对比改造前后属性列表 |
| Service 层抽取导致查询行为变化 | 中（数据不一致） | 低 | B04 的 dashboard/history/llm_config 都是纯查询逻辑，抽取不改变 SQL；改完一个验证一个端点 |
| task_queue 拆分导致异步任务失败 | 高（检测任务卡住） | 中 | B05 拆分时保持原有方法签名不变，仅移动函数位置；改造后手动提交一个检测任务验证完整流程 |
| LayoutShell 导致视图渲染异常 | 中（页面白屏） | 低 | F03 的 slot 透传是 Vue 原生特性，逐个视图替换并手动检查 |
| Store 引入导致状态不一致 | 中（UI 数据不同步） | 低 | F01 的 TaskStore 仅做统一封装，不改变数据流方向 |

### 6.2 回滚策略

每个任务独立可回滚：

```bash
# 回滚单个任务（假设每个任务一个独立 commit）
git revert <commit-hash>

# 如果是紧急回滚，直接 reset 到任务前
git reset --hard <pre-task-commit>
```

任务之间无强耦合（B01→B03 的依赖只影响导入便利性，不阻塞后续任务），因此支持选择性回滚——例如 B04 出问题只回滚 B04，B01/B02/B03 的改动不受影响。

### 6.3 验证检查清单

每个任务完成后执行：

**后端**：
- [ ] `python -m app.main` 服务正常启动
- [ ] `curl http://localhost:8000/api/health` 返回 200
- [ ] 涉及的路由端点逐个 `curl` 验证
- [ ] 无新增的 `ImportError` 或循环导入警告

**前端**：
- [ ] `npm run build` 无 TypeScript 编译错误
- [ ] `npm run dev` 页面正常渲染
- [ ] 涉及的视图/组件手动操作验证
- [ ] 浏览器 Console 无新增报错
