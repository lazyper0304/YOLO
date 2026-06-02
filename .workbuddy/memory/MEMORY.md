# yolo_detection_platform 项目记忆

## 技术栈
- 后端: Python FastAPI + SQLAlchemy 2.0 async + aiomysql + Redis + ultralytics YOLO
- 前端: Vue 3 + Vite + TypeScript + Pinia + Element Plus + Tailwind CSS
- 数据库: MySQL (持久化) + Redis (缓存)

## 项目结构
- `backend/` — FastAPI 后端 (三层架构: API → Service → Data)
- `frontend/` — Vue 3 SPA 前端
- `docs/` — PRD.md + ARCHITECTURE.md

## 关键约定
- API统一格式: `{code, message, data}`
- JWT Bearer Token 认证, 24h过期
- 前端路由守卫: 未登录 → /login
- LLM适配器模式: OpenAIAdapter / ClaudeAdapter / GenericOpenAIAdapter
- YOLO单例+LRU缓存(最多2模型常驻)

## 当前状态
T01-T04 MVP 已完成并测试通过 (104/104 tests)
T05 (视频/摄像头/历史记录集成) 待实现
