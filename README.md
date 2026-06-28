# YOLO 目标检测与分析平台

> **版本:** 1.1.0 | **技术栈:** YOLOv26 + FastAPI + Vue 3 + MySQL + Redis + ChromaDB

基于 YOLOv26 与多模态大模型协同的目标检测与分析平台。支持图片、视频、本机摄像头三种输入源，提供 YOLO 纯检测、LLM 纯分析和 YOLO+LLM 协同三种检测模式，内置知识库管理、RAG 智能问答、知识图谱可视化和数据仪表盘等模块。

---

## 目录

- [技术栈](#技术栈)
- [环境要求](#环境要求)
- [快速启动](#快速启动)
- [功能概览](#功能概览)
- [三种检测模式](#三种检测模式)
- [项目结构](#项目结构)
- [API 概览](#api-概览)
- [配置说明](#配置说明)
- [运行测试](#运行测试)
- [常见问题](#常见问题)

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Vite + TypeScript + Pinia + Element Plus + Tailwind CSS + ECharts + D3.js |
| 后端 | Python FastAPI + Uvicorn + SQLAlchemy 2.0 async + aiomysql |
| AI 引擎 | Ultralytics YOLOv26 + PyTorch + OpenCV + 多模态 LLM 适配器 (OpenAI/Claude/Ollama) |
| 向量检索 | ChromaDB (HNSW 索引) + 嵌入模型 (OpenAI 兼容 API / DashScope) |
| 持久化存储 | MySQL 8.0 |
| 缓存与实时 | Redis 5.0+ (缓存/会话/进度追踪) |

---

## 环境要求

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.13+ | 后端运行环境 |
| Node.js | 18+ | 前端构建 |
| MySQL | 8.0 | 持久化存储 |
| Redis | 5.0+ | 缓存 / 进度追踪 / 会话管理 |

---

## 快速启动

### 1. 克隆仓库

```powershell
git clone https://github.com/lazyper0304/YOLO.git
cd YOLO
```

### 2. 创建并激活虚拟环境

**方式 A：Python venv（推荐）**

```powershell
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat

# Linux / macOS
source .venv/bin/activate
```

**方式 B：Anaconda**

```powershell
conda create -n yolo python=3.13 -y
conda activate yolo
```

### 3. 初始化数据库

确保 MySQL 服务已运行，然后导入数据库结构：

```powershell
# 使用初始化脚本（推荐首次安装，包含完整表结构+数据）
mysql -u root -p < sql\init_database.sql

# 或仅创建空数据库
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS yolo_detection CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### 4. 启动 Redis

```powershell
.\Redis-8.8.0-Windows-x64-cygwin-with-Service\redis-server.exe
```

### 5. 配置后端环境变量

```powershell
cd backend
copy .env.example .env
```

编辑 `backend\.env`，至少修改以下两项：

```ini
MYSQL_PASSWORD=你的MySQL密码
SECRET_KEY=随机生成32位以上字符串
```

### 6. 安装后端依赖

```powershell
cd backend
pip install -r requirements.txt

# 如果已通过 init_database.sql 初始化，则 stamp 版本
alembic stamp head

# 如果使用空数据库，则自动创建所有表
# alembic upgrade head
```

### 7. 安装前端依赖

```powershell
cd frontend
npm install
```

### 8. 启动服务

```powershell
# 终端1 — 后端
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

# 终端2 — 前端
cd frontend
npm run dev
```

| 服务 | 地址 |
|------|------|
| 前端页面 | http://localhost:5173 |
| 后端 API | http://localhost:8001 |
| API 文档 (Swagger) | http://localhost:8001/docs |

---

## 功能概览

### 目标检测

- **图片检测** — 上传图片，YOLO/LLM/协同三种模式实时返回结果
- **视频检测** — 上传视频（MP4/AVI/MOV），帧间隔 1-300 秒可配，异步后台处理
- **本机摄像头实时检测** — 浏览器 Webcam 实时推流，每 500ms 截帧 + 边界框 Canvas 叠加
- **YOLOv26 端到端推理** — 无 NMS 后处理，GPU 下 30-50ms/张
- **模型管理** — 上传自定义 .pt 模型，运行时切换，LRU 缓存（最多 2 个常驻）
- **LLM 多供应商** — 支持 OpenAI / Claude / Ollama 自动路由切换

### 知识库 (RAG)

- **多格式文档上传** — PDF / DOCX / MD / TXT / 图片（JPG/PNG/WEBP/BMP）
- **自动处理流水线** — 解析 → OCR → 分块 (tiktoken) → 去重 (SHA256) → 嵌入 → ChromaDB 存储
- **实时进度追踪** — Redis 驱动的处理进度展示（百分比 + 当前步骤）
- **语义检索** — ChromaDB HNSW 索引 + 余弦相似度检索
- **RAG 流式问答** — SSE 协议逐 token 推送，多会话管理

### 知识图谱

- **自动构建** — jieba 关键词提取 → Embedding 语义聚类 → 共现关系构建
- **可视化** — D3.js 力导向图，节点颜色区分类型，支持缩放拖拽
- **交互式浏览** — 点击节点查看关联文档片段

### 数据仪表盘

- **ECharts 可视化** — 近 14 天检测趋势折线图
- **模式分布** — 三种检测模式的占比饼图
- **模型调用统计** — YOLO/LLM/OCR/Embedding 调用次数柱状图
- **系统监控** — CPU / 内存 / 并发任务实时面板

### 智能助手

- 检测结果的自然语言问答
- 知识库内容的检索增强问答
- LLM 辅助生成视频分析提示词
- 多会话支持（历史持久化 Redis）

### 其他

- JWT 认证（注册 / 登录 / Token 24h 过期）
- 检测历史记录（搜索 / 筛选 / 批量删除）
- 模型调用日志（ModelCallLog 持久化审计）
- 任务列表管理（暂停 / 恢复 / 取消）

---

## 三种检测模式

| 模式 | 处理流程 | 适用场景 |
|------|---------|---------|
| **YOLO 纯检测** | 输入图片 → YOLO 推理 → 边界框 + 类别 + 置信度 | 实时定位、数量统计 |
| **LLM 纯分析** | 输入图片 → 多模态 LLM → 自然语言描述（摘要+对象+分析） | 复杂场景语义理解 |
| **协同模式** | YOLO 检测 → 裁剪目标区域 → LLM 逐区域分析 → 融合输出 | 同时需要位置+语义 |

协同模式支持**全图分析**（LLM 参考完整图片综合描述）和**区域分析**（仅裁剪区域送 LLM，token 减少 60-80%）两种范围。

---

## 项目结构

```
YOLO/
├── backend/
│   ├── app/
│   │   ├── api/                  # REST & SSE 路由
│   │   │   ├── auth.py           # 用户认证
│   │   │   ├── detection.py      # 图片检测
│   │   │   ├── tasks.py          # 视频/摄像头异步任务
│   │   │   ├── knowledge_base.py # 知识库 CRUD + 文档 + 图谱
│   │   │   ├── chat.py           # 智能助手对话
│   │   │   ├── dashboard.py      # 仪表盘数据
│   │   │   └── ...
│   │   ├── core/                 # 基础设施
│   │   │   ├── database.py       # SQLAlchemy 连接
│   │   │   ├── security.py       # JWT + bcrypt + AES 加密
│   │   │   └── redis_client.py   # Redis 客户端
│   │   ├── models/               # ORM 模型
│   │   │   ├── detection_record.py, user.py, yolo_model.py
│   │   │   ├── llm_config.py, ocr_config.py, embedding_config.py
│   │   │   ├── knowledge_base.py, model_call_log.py
│   │   │   └── ...
│   │   ├── services/             # 业务逻辑层
│   │   │   ├── yolo_service.py           # YOLO 引擎（单例+LRU+混合推理）
│   │   │   ├── llm_service.py            # LLM 多供应商适配器
│   │   │   ├── document_service.py       # 文档处理流水线
│   │   │   ├── entity_service.py         # 知识图谱实体提取
│   │   │   ├── chroma_service.py         # ChromaDB 向量检索
│   │   │   ├── embedding_service.py      # 嵌入模型
│   │   │   ├── dedup_service.py          # 文本去重
│   │   │   ├── model_call_service.py     # 调用日志
│   │   │   ├── task_queue.py             # 异步任务队列
│   │   │   └── processors/               # 视频/摄像头处理器
│   │   │       ├── video_processor.py
│   │   │       ├── frame_analysis_processor.py
│   │   │       └── camera_processor.py
│   │   └── config/               # 配置
│   │       ├── settings.py
│   │       └── yolo.py
│   ├── alembic/                  # 数据库迁移
│   ├── tests/                    # 104 个单元测试
│   ├── uploads/                  # 上传文件存储
│   ├── models/                   # YOLO 模型文件
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── api/                  # API 封装（axios）
│       ├── components/           # 可复用组件
│       │   ├── detection/
│       │   ├── knowledge/        # KBSidebar, KBDocumentTable, KnowledgeGraphPanel
│       │   └── ...
│       ├── stores/               # Pinia 状态管理
│       ├── composables/          # useCamera, useTaskList
│       ├── views/                # 页面
│       │   ├── AuthView.vue              # 登录注册
│       │   ├── DetectionView.vue         # 检测主页
│       │   ├── KnowledgeBaseView.vue     # 知识库管理
│       │   ├── ChatView.vue              # 智能助手
│       │   ├── DashboardView.vue         # 数据仪表盘
│       │   └── ...
│       └── types/                # TypeScript 类型定义
├── sql/
│   └── init_database.sql         # 数据库初始化（建表+外键+索引）
├── docs/                         # 文档
│   ├── PRD.md                    # 产品需求文档
│   ├── ARCHITECTURE.md           # 架构设计
│   └── team_members.md           # 团队分工
├── Redis-8.8.0-Windows-x64-cygwin-with-Service/  # Redis 绿色版
├── VERSION                       # 1.1.0
└── README.md
```

---

## API 概览

| 前缀 | 说明 | 主要端点 |
|------|------|---------|
| `/api/auth` | 用户认证 | 注册、登录、刷新 Token |
| `/api/detection` | 图片检测 | 单张检测、实时检测 |
| `/api/tasks` | 异步任务 | 创建/查询/删除/暂停恢复视频+摄像头任务 |
| `/api/history` | 历史记录 | 搜索、筛选、批量删除 |
| `/api/chat` | 智能助手 | SSE 流式对话、提示词生成 |
| `/api/knowledge-bases` | 知识库 | CRUD、文档上传/删除、图谱提取 |
| `/api/rag-chat` | RAG 问答 | SSE 流式知识库问答 |
| `/api/llm-configs` | LLM 配置 | 多供应商配置管理 |
| `/api/yolo-models` | YOLO 模型 | 模型上传、切换、列表查询 |
| `/api/embedding-configs` | 嵌入模型配置 | 多配置管理 |
| `/api/ocr-config` | OCR 配置 | API Key 管理 |
| `/api/dashboard` | 仪表盘 | 统计数据、趋势、模型调用分布 |

---

## 配置说明

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `MYSQL_HOST` | localhost | MySQL 地址 |
| `MYSQL_PORT` | 3306 | MySQL 端口 |
| `MYSQL_USER` | root | MySQL 用户 |
| `MYSQL_PASSWORD` | — | MySQL 密码（**必须修改**） |
| `MYSQL_DATABASE` | yolo_detection | 数据库名 |
| `REDIS_HOST` | localhost | Redis 地址 |
| `REDIS_PORT` | 6379 | Redis 端口 |
| `SECRET_KEY` | — | JWT + Fernet AES 加密密钥（**必须修改**） |
| `YOLO_DEFAULT_MODEL` | yolo26n.pt | 默认检测模型 |
| `YOLO_CONFIDENCE_THRESHOLD` | 0.25 | 检测置信度阈值 |
| `BACKEND_PORT` | 8001 | 后端服务端口 |
| `LLM_TIMEOUT_SECONDS` | 60 | LLM API 超时 |
| `EMBEDDING_TIMEOUT_SECONDS` | 120 | 嵌入 API 超时 |

---

## 运行测试

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/ -v
```

项目共包含 **104 个单元测试用例**，覆盖用户认证、图片检测、视频任务、知识库、知识图谱和配置管理六大模块。

---

## 常见问题

**Q: 图片不显示 / 视频加载失败**
A: 确保 Vite 开发服务器正在运行，前端代理配置为将 `/api` 和 `/uploads` 转发到后端 8001 端口。

**Q: 知识库文档一直显示"等待处理"**
A: 检查是否已配置并激活了嵌入模型（模型管理 → 嵌入模型管理），以及 LLM 是否已激活。文档处理流水线依赖这两个服务。

**Q: LLM 调用报密钥解密失败**
A: 修改 `SECRET_KEY` 会导致已加密的 API Key 无法解密。请在模型管理页面重新输入并保存所有 LLM 配置。

**Q: YOLO 模型未找到**
A: 首次启动会自动下载 `yolo26n.pt`（约 5MB），也可在模型管理页上传自定义 `.pt` 文件。系统兼容 YOLOv8 至 v26 的权重文件。

**Q: MySQL 连接失败**
A: 检查 `.env` 中 `MYSQL_PASSWORD` 是否正确配置，确认 MySQL 8.0 服务已启动。

**Q: Redis 连接失败**
A: 确认已运行 `redis-server.exe`。Redis 不可用时，部分功能降级运行（禁用缓存和进度追踪），不影响核心检测功能。

---

## 许可证

本项目为 YOLO 目标检测与分析平台，基于开源技术栈构建。
