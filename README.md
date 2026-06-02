# 图像目标检测与分析平台

基于 YOLO + 多模态大模型协同的图像目标检测平台，支持图片/视频/摄像头输入，三种工作模式自由切换。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Vite + TypeScript + Pinia + Element Plus + Tailwind CSS |
| 后端 | Python FastAPI + SQLAlchemy 2.0 async + Redis |
| AI | ultralytics YOLO + 多模态大模型（OpenAI/Claude适配器） |
| 数据库 | MySQL 8.0 + Redis |

## 环境要求

| 依赖 | 最低版本 | 说明 |
|---|---|---|
| Python | 3.13+ | 推荐使用项目自带 `.venv` |
| Node.js | 18+ | 前端构建 |
| MySQL | 8.0 | 持久化存储 |
| Redis | 5.0+ | 缓存/实时数据 |

---

## 快速启动

### 1. 启动 MySQL

确保 MySQL 服务已运行，并创建数据库：

```sql
CREATE DATABASE IF NOT EXISTS yolo_detection CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Windows 下检查 MySQL 服务：
```powershell
Get-Service -Name MySQL80
# 如果未运行：Start-Service MySQL80
```

### 2. 启动 Redis

```powershell
cd Redis-8.8.0-Windows-x64-cygwin-with-Service
.\redis-server.exe
```

看到 ASCII art 和 `Ready to accept connections tcp` 即启动成功。

### 3. 配置后端

```powershell
cd backend

# 复制并编辑环境变量
copy .env.example .env
```

编辑 `backend\.env`，修改以下配置：

```ini
# 数据库（必改）
MYSQL_PASSWORD=你的MySQL密码

# 安全（建议修改）
SECRET_KEY=随机生成一个32位以上字符串
```

其他配置项有默认值，可按需调整。

### 4. 安装依赖 & 初始化数据库

```powershell
# 激活虚拟环境
..\.venv\Scripts\activate

# 安装 Python 依赖（首次）
pip install -r requirements.txt

# 初始化数据库表
alembic upgrade head
```

### 5. 启动后端

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8888
```

看到 `Application startup complete` 即成功。
API 文档自动生成：http://localhost:8888/docs

### 6. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

前端开发服务器默认运行在 http://localhost:5173

---

## 使用流程

1. **注册/登录** — 首次使用需注册账号
2. **配置 LLM** — 设置 → 添加 LLM API（OpenAI/Claude 兼容接口即可）
3. **选择工作模式** — 纯 YOLO / 纯 LLM / 协同
4. **上传图片** — 拖拽或点击上传
5. **开始检测** — 点击检测按钮，查看结果

> 首次检测时 YOLO 会自动下载默认模型 `yolov8n.pt`（约 6MB），可能需要等待几秒。

---

## 三种工作模式

| 模式 | 说明 |
|---|---|
| **纯 YOLO** | 仅目标检测，输出边界框 + 类别 + 置信度 |
| **纯 LLM** | 仅多模态大模型分析，输出结构化自然语言描述 |
| **协同** | YOLO 先检测目标区域 → 裁剪 → LLM 逐区域分析 → 汇总结果 |

---

## 项目结构

```
end/
├── backend/                # FastAPI 后端
│   ├── app/
│   │   ├── api/            # REST & WebSocket 路由
│   │   ├── core/           # 数据库、Redis、安全
│   │   ├── models/         # SQLAlchemy ORM 模型
│   │   ├── schemas/        # Pydantic 数据校验
│   │   ├── services/       # 业务逻辑（YOLO/LLM/检测编排）
│   │   └── utils/          # 工具函数
│   ├── alembic/            # 数据库迁移
│   ├── tests/              # 单元测试（110 用例）
│   └── requirements.txt
├── frontend/               # Vue 3 SPA
│   └── src/
│       ├── api/            # Axios API 封装
│       ├── components/     # Vue 组件
│       ├── composables/    # 组合式函数
│       ├── stores/         # Pinia 状态管理
│       ├── types/          # TypeScript 类型
│       └── views/          # 页面组件
├── docs/                   # 设计文档
│   ├── PRD.md              # 产品需求文档
│   └── ARCHITECTURE.md     # 系统架构设计
├── .venv/                  # Python 虚拟环境
└── Redis-8.8.0-.../        # Redis 绿色版
```

---

## 运行测试

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests/ -v
```

## 常见问题

**Q: YOLO 检测报 500 错误**
A: 首次使用会自动下载 `yolov8n.pt` 模型（约6MB），等待几秒后重试。

**Q: MySQL 连接失败 `Access denied`**
A: 检查 `.env` 中的 `MYSQL_PASSWORD` 是否正确。

**Q: 前端请求报 CORS 错误**
A: 确保后端 `CORS_ORIGINS` 包含前端地址，默认配置 `http://localhost:5173`。

**Q: Redis 连接失败**
A: 确保 Redis 已启动且端口 6379 未被占用。
