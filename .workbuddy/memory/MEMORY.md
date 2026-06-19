# yolo_detection_platform 项目记忆

## 技术栈
- 后端: Python FastAPI + SQLAlchemy 2.0 async + aiomysql + Redis + ultralytics YOLO
- 前端: Vue 3 + Vite + TypeScript + Pinia + Element Plus + Tailwind CSS
- 数据库: MySQL (持久化) + Redis (缓存)

## 项目结构
- `backend/` — FastAPI 后端 (三层架构: API → Service → Data)
- `frontend/` — Vue 3 SPA 前端
- `docs/` — PRD.md + ARCHITECTURE.md
- `Redis-8.8.0-Windows-x64-cygwin-with-Service/` — Redis 绿色版

## 关键约定
- API统一格式: `{code, message, data}`
- JWT Bearer Token 认证, 24h过期
- 前端路由守卫: 未登录 → /login
- LLM适配器模式: OpenAIAdapter / ClaudeAdapter / GenericOpenAIAdapter / OllamaAdapter
- YOLO单例+LRU缓存(最多2模型常驻)
- 数据库版本管理: alembic
- **检测任务不限时**：`TASK_TIMEOUT_SECONDS = None`，已移除 `asyncio.wait_for(timeout=300)` 包装；用户可通过 `DELETE /api/tasks/{id}` 或 `CancelledError` 手动终止

## 当前状态
- T01-T04 MVP 已完成并测试通过 (104/104 tests)
- T05 视频/摄像头/历史记录基本实现
- **2026-06-03** T05增强: LLM视频帧分析功能已实现

## T05 增强功能 — LLM视频帧分析

### 新增能力
1. **可配置帧截取间隔**: 创建视频/摄像头任务时设置 `frame_interval_seconds`(1-300秒)
2. **LLM逐帧分析**: 视频和IP摄像头支持 `llm_only` 和 `collaborative` 模式
3. **全视频主题分析提示词**: `analysis_prompt` 字段，通过 ChatView "生成提示词" 模式由 LLM 生成
4. **本机摄像头 LLM 模式**: 前端定时截帧 → POST /api/tasks/{id}/analyze-frame → 异步 LLM 分析
5. **预估耗时**: 创建任务时根据视频时长+帧间隔+LLM延迟估算处理时间
6. **进度追踪**: `progress` 字段(0-100), 中途可查看已完成帧的结果
7. **帧结果浏览**: 任务详情对话框支持逐帧查看 bboxes + LLM 分析

### 数据库变更
- `detection_records` 新增3个字段: `frame_interval_seconds INT`(默认5), `analysis_prompt TEXT`, `progress INT`(默认0)

### 新增/修改的API
- `POST /api/tasks` 新增参数: `frame_interval_seconds`, `analysis_prompt`; 返回 `estimated_frame_count`, `estimated_duration_seconds`
- `POST /api/tasks/{id}/analyze-frame` 新增: 前端提交摄像头帧进行LLM分析
- `POST /api/chat/generate-prompt` 新增: LLM对话生成分析提示词
- `GET /api/tasks`, `GET /api/tasks/{id}` 返回新增 `frame_interval_seconds`, `progress`, `analysis_prompt`

### 前端变更
- `DetectionView.vue`: 帧间隔滑块、分析提示词输入、"从对话生成提示词"按钮、预估耗时显示、摄像头LLM模式、帧结果浏览
- `ChatView.vue`: 新增"生成提示词"模式标签页
- `types/api.ts`, `types/detection.ts`: 新增 `FrameAnalysisResult`, `VideoAnalysisConfig`, `GeneratedPrompt` 类型
- `api/detection.ts`: 新增 `analyzeFrame()`, `generatePrompt()` 方法

### 数据流
```
创建任务(帧间隔+提示词) → TaskQueue轮询 → 按间隔截帧 → 
每帧: YOLO(可选) → LLM分析(含主题提示词) → 进度更新 → 
result_json.frames[] → 前端逐帧浏览
```
