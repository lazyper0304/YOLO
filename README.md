# YOLO 目标检测与分析平台

基于 YOLO + 多模态大模型协同的图像目标检测平台，集成知识库 RAG 问答，支持图片/视频/摄像头多源输入。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Vite + TypeScript + Pinia + Element Plus + Tailwind CSS |
| 后端 | Python FastAPI + SQLAlchemy 2.0 async + aiomysql + Redis |
| AI 引擎 | ultralytics YOLO (v8/v10/v11) + 多模态 LLM 适配器 |
| 向量检索 | ChromaDB + 嵌入模型 (OpenAI 兼容 API) |
| 数据库 | MySQL 8.0 (持久化) + Redis (缓存/实时) |

## 环境要求

| 依赖 | 最低版本 | 说明 |
|---|---|---|
| Python | 3.13+ | 推荐使用项目自带 `.venv` |
| Node.js | 18+ | 前端构建 |
| MySQL | 8.0 | 持久化存储 |
| Redis | 5.0+ | 缓存 / 进度追踪 |

---

## 快速启动

### 1. 启动 MySQL

确保 MySQL 服务已运行，并创建数据库：

```sql
CREATE DATABASE IF NOT EXISTS yolo_detection CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. 启动 Redis

```powershell
cd Redis-8.8.0-Windows-x64-cygwin-with-Service
.\redis-server.exe
```

### 3. 配置后端

```powershell
cd backend
copy .env.example .env
```

编辑 `backend\.env`，修改数据库密码：

```ini
MYSQL_PASSWORD=你的MySQL密码
SECRET_KEY=随机生成32位以上字符串
```

### 4. 安装依赖

```powershell
cd backend
..\.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
```

### 5. 启动服务

```powershell
# 终端1 — 后端
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端2 — 前端
cd frontend
npm install
npm run dev
```

| 服务 | 地址 |
|---|---|
| 前端 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| API 文档 (Swagger) | http://localhost:8000/docs |

---

## 功能概览

### 目标检测
- **图片检测** — 上传图片，实时返回检测结果
- **视频检测** — 上传视频，按间隔截帧逐帧分析
- **摄像头检测** — 浏览器调用摄像头，实时推流 + 定时截帧检测
- **三种工作模式** — 纯 YOLO / 纯 LLM / 协同
- **模型管理** — 上传自定义 `.pt` 模型，运行时切换
- **LLM 配置** — 支持 OpenAI、Claude、Ollama 等兼容接口

### 知识库 (RAG)
- **文档上传** — 支持 PDF、DOCX、MD、TXT 及图片
- **自动处理** — 解析 → 分块 → 嵌入 → 向量存储，全自动
- **Redis 进度追踪** — 实时显示处理步骤和百分比
- **向量检索** — ChromaDB 语义搜索
- **知识库问答** — 基于知识库内容的 SSE 流式对话

### 智能助手
- **检测结果问答** — 对检测结果的自然语言提问
- **知识库问答** — 选中知识库后，LLM 结合检索结果回答
- **提示词生成** — LLM 辅助生成视频分析提示词
- **多会话支持** — 对话历史持久化到 Redis

### 其他
- JWT 认证 + 注册登录
- 检测历史记录 / 搜索 / 批量删除
- 数据看板 (Dashboard)
- 任务列表管理

---

## 三种检测模式

| 模式 | 流程 |
|---|---|
| **纯 YOLO** | 图片 → YOLO 推理 → 边界框 + 类别 + 置信度 |
| **纯 LLM** | 图片 → 多模态 LLM → 自然语言描述 |
| **协同** | 图片 → YOLO 检测区域 → 裁剪 → LLM 逐区域分析 → 汇总 |

---

## 项目结构

```
end/
├── backend/
│   ├── app/
│   │   ├── api/              # REST & SSE 路由
│   │   │   ├── auth.py       # 认证
│   │   │   ├── chat.py       # 智能助手对话
│   │   │   ├── detection.py  # 检测任务
│   │   │   ├── knowledge_base.py  # 知识库 CRUD
│   │   │   ├── rag_chat.py   # RAG 流式问答
│   │   │   └── ...
│   │   ├── core/             # 数据库 / Redis / 安全 / 加密
│   │   ├── models/           # SQLAlchemy ORM 模型
│   │   ├── schemas/          # Pydantic 校验
│   │   └── services/         # 业务逻辑
│   │       ├── detection_service.py  # 检测编排
│   │       ├── yolo_service.py       # YOLO 单例 + LRU 缓存
│   │       ├── document_service.py    # 文档生命周期
│   │       ├── embedding_service.py   # 嵌入向量
│   │       ├── chroma_service.py      # ChromaDB
│   │       ├── retrieval_service.py   # 知识检索
│   │       ├── kb_progress.py         # Redis 进度追踪
│   │       └── ...
│   ├── alembic/              # 数据库迁移
│   ├── tests/                # 单元测试
│   ├── uploads/              # 上传文件存储
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── api/              # API 封装
│       ├── components/       # 通用组件
│       ├── stores/           # Pinia 状态管理
│       ├── types/            # TypeScript 类型
│       └── views/            # 页面
│           ├── DetectionView.vue      # 检测页面
│           ├── KnowledgeBaseView.vue  # 知识库管理
│           ├── ChatView.vue           # 智能助手
│           ├── HistoryView.vue        # 历史记录
│           ├── DashboardView.vue      # 数据看板
│           └── ModelsView.vue         # 模型管理
├── docs/
│   ├── PRD.md                # 产品需求文档
│   └── ARCHITECTURE.md       # 系统架构设计
└── Redis-8.8.0-Windows-x64-cygwin-with-Service/  # Redis 绿色版
```

---

## API 概览

| 前缀 | 说明 |
|---|---|
| `/api/auth` | 注册 / 登录 / Token 刷新 |
| `/api/detection` | 图片 / 视频 / 摄像头检测 |
| `/api/tasks` | 任务管理 (创建 / 列表 / 删除 / 进度) |
| `/api/history` | 历史记录查询 |
| `/api/chat` | 智能助手流式对话 |
| `/api/knowledge-bases` | 知识库 CRUD / 文档管理 / 检索 |
| `/api/rag-chat` | RAG 流式问答 |
| `/api/llm-configs` | LLM 配置管理 |
| `/api/yolo-models` | YOLO 模型管理 |
| `/api/embedding-configs` | 嵌入模型配置 |

---

## 配置说明

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MYSQL_HOST` | localhost | 数据库地址 |
| `MYSQL_PORT` | 3306 | 数据库端口 |
| `MYSQL_USER` | root | 数据库用户 |
| `MYSQL_PASSWORD` | — | 数据库密码 |
| `REDIS_HOST` | localhost | Redis 地址 |
| `REDIS_PORT` | 6379 | Redis 端口 |
| `SECRET_KEY` | — | JWT + Fernet 加密密钥 |
| `BACKEND_PORT` | 8000 | 后端端口 |
| `YOLO_DEFAULT_MODEL` | yolov8n.pt | 默认检测模型 |
| `LLM_TIMEOUT_SECONDS` | 60 | LLM 请求超时 |
| `EMBEDDING_TIMEOUT_SECONDS` | 120 | 嵌入 API 超时 |
| `RAG_CHUNK_SIZE` | 512 | 文档分块大小 |
| `RAG_TOP_K` | 5 | 检索返回数 |

---

## 运行测试

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests/ -v
```

## 常见问题

**Q: 图片不显示 / 视频加载失败**
A: 确保前端 Vite 开发服务器运行中，代理会将 `/uploads` 转发到后端 8000 端口。

**Q: 知识库文档一直"等待处理"**
A: 检查是否配置并启用了嵌入模型（模型管理 → 嵌入模型管理），以及 LLM 是否已激活。

**Q: LLM 调用报 API 密钥解密失败**
A: `SECRET_KEY` 变更导致加密的 API Key 无法解密，请在模型管理页面重新输入并保存。

**Q: YOLO 模型未找到**
A: 首次使用会自动下载 `yolov8n.pt`（约 6MB），也可在模型管理页上传自定义 `.pt` 文件。

**Q: MySQL 连接失败**
A: 检查 `.env` 中 `MYSQL_PASSWORD`，确认 MySQL 服务已启动。

**Q: Redis 连接失败**
A: 确认 Redis 已启动。Redis 不可用时部分功能降级（禁用缓存和进度追踪），不影响核心检测。
