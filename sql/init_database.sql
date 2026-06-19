-- =============================================================================
-- YOLO 目标检测平台 — 数据库初始化脚本
-- 生成时间: 2026-06-19
-- 数据库: MySQL 8.0+
-- 使用方法: mysql -u root -p < init_database.sql
-- =============================================================================

CREATE DATABASE IF NOT EXISTS yolo_detection
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE yolo_detection;

-- ─── 用户 ────────────────────────────────────────────────────────────────
CREATE TABLE users (
  id            INT           NOT NULL AUTO_INCREMENT,
  username      VARCHAR(50)   NOT NULL,
  email         VARCHAR(255)  NOT NULL,
  password_hash VARCHAR(255)  NOT NULL,
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE INDEX ix_users_username (username),
  UNIQUE INDEX ix_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── LLM 配置 ─────────────────────────────────────────────────────────────
CREATE TABLE llm_configs (
  id            INT           NOT NULL AUTO_INCREMENT,
  user_id       INT           NOT NULL,
  name          VARCHAR(100)  NOT NULL,
  api_base_url  VARCHAR(500)  NOT NULL,
  api_key       TEXT          NOT NULL,
  model_name    VARCHAR(100)  NOT NULL,
  provider      VARCHAR(50)   NOT NULL,
  is_active     TINYINT(1)    NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  INDEX ix_llm_configs_user_id (user_id),
  CONSTRAINT llm_configs_ibfk_1 FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── YOLO 模型 ────────────────────────────────────────────────────────────
CREATE TABLE yolo_models (
  id            INT           NOT NULL AUTO_INCREMENT,
  user_id       INT           NOT NULL,
  name          VARCHAR(100)  NOT NULL,
  file_path     VARCHAR(500)  NOT NULL,
  model_type    VARCHAR(50)   NOT NULL,
  is_builtin    TINYINT(1)    NOT NULL DEFAULT 0,
  file_size     INT           NOT NULL DEFAULT 0,
  classes       TEXT          NULL,
  is_active     TINYINT(1)    NOT NULL DEFAULT 0,
  uploaded_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX ix_yolo_models_user_id (user_id),
  CONSTRAINT yolo_models_ibfk_1 FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── 检测记录 ─────────────────────────────────────────────────────────────
CREATE TABLE detection_records (
  id                      INT           NOT NULL AUTO_INCREMENT,
  user_id                 INT           NOT NULL,
  source_type             VARCHAR(20)   NOT NULL,
  source_path             VARCHAR(500)  NOT NULL,
  mode                    VARCHAR(30)   NOT NULL,
  task_name               VARCHAR(200)  NULL,
  yolo_model_id           INT           NULL,
  llm_config_id           INT           NULL,
  result_json             JSON          NULL,
  status                  VARCHAR(20)   NOT NULL DEFAULT 'completed',
  thumbnail_path          VARCHAR(500)  NULL,
  created_at              DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  frame_interval_seconds  INT           NOT NULL DEFAULT 5,
  analysis_prompt         TEXT          NULL,
  progress                INT           NOT NULL DEFAULT 0,
  llm_analysis_scope      VARCHAR(20)   NOT NULL DEFAULT 'full',
  PRIMARY KEY (id),
  INDEX ix_detection_records_user_id (user_id),
  INDEX yolo_model_id (yolo_model_id),
  INDEX llm_config_id (llm_config_id),
  CONSTRAINT detection_records_ibfk_1 FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT detection_records_ibfk_2 FOREIGN KEY (yolo_model_id) REFERENCES yolo_models(id) ON DELETE SET NULL,
  CONSTRAINT detection_records_ibfk_3 FOREIGN KEY (llm_config_id) REFERENCES llm_configs(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── 知识库 ───────────────────────────────────────────────────────────────
CREATE TABLE knowledge_bases (
  id              INT           NOT NULL AUTO_INCREMENT,
  user_id         INT           NOT NULL,
  name            VARCHAR(200)  NOT NULL,
  description     TEXT          NULL,
  embedding_model VARCHAR(200)  NOT NULL DEFAULT 'default',
  status          VARCHAR(20)   NOT NULL DEFAULT 'active',
  document_count  INT           NOT NULL DEFAULT 0,
  chunk_count     INT           NOT NULL DEFAULT 0,
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX ix_knowledge_bases_user_id (user_id),
  CONSTRAINT knowledge_bases_ibfk_1 FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── 知识库文档 ───────────────────────────────────────────────────────────
CREATE TABLE kb_documents (
  id                INT           NOT NULL AUTO_INCREMENT,
  knowledge_base_id INT           NOT NULL,
  user_id           INT           NOT NULL,
  filename          VARCHAR(500)  NOT NULL,
  file_path         VARCHAR(500)  NOT NULL,
  file_type         VARCHAR(20)   NOT NULL,
  file_size         INT           NOT NULL,
  status            VARCHAR(20)   NOT NULL,
  error_message     TEXT          NULL,
  chunk_count       INT           NOT NULL DEFAULT 0,
  created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX ix_kb_documents_knowledge_base_id (knowledge_base_id),
  INDEX ix_kb_documents_user_id (user_id),
  CONSTRAINT kb_documents_ibfk_1 FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  CONSTRAINT kb_documents_ibfk_2 FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── 知识库片段 ───────────────────────────────────────────────────────────
CREATE TABLE kb_chunks (
  id                INT           NOT NULL AUTO_INCREMENT,
  document_id       INT           NOT NULL,
  knowledge_base_id INT           NOT NULL,
  chunk_index       INT           NOT NULL,
  content           TEXT          NOT NULL,
  metadata_json     JSON          NULL,
  token_count       INT           NOT NULL,
  chroma_id         VARCHAR(100)  NULL,
  created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX ix_kb_chunks_document_id (document_id),
  INDEX ix_kb_chunks_knowledge_base_id (knowledge_base_id),
  CONSTRAINT kb_chunks_ibfk_1 FOREIGN KEY (document_id) REFERENCES kb_documents(id) ON DELETE CASCADE,
  CONSTRAINT kb_chunks_ibfk_2 FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── 知识图谱实体 ─────────────────────────────────────────────────────────
CREATE TABLE kb_entities (
  id                INT           NOT NULL AUTO_INCREMENT,
  knowledge_base_id INT           NOT NULL,
  name              VARCHAR(200)  NOT NULL,
  entity_type       VARCHAR(50)   NOT NULL,
  description       TEXT          NULL,
  metadata_json     JSON          NULL,
  created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX ix_kb_entities_knowledge_base_id (knowledge_base_id),
  CONSTRAINT kb_entities_ibfk_1 FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── 知识图谱关系 ─────────────────────────────────────────────────────────
CREATE TABLE kb_relations (
  id                INT           NOT NULL AUTO_INCREMENT,
  knowledge_base_id INT           NOT NULL,
  source_id         INT           NOT NULL,
  target_id         INT           NOT NULL,
  relation_type     VARCHAR(50)   NOT NULL,
  created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX ix_kb_relations_knowledge_base_id (knowledge_base_id),
  INDEX source_id (source_id),
  INDEX target_id (target_id),
  CONSTRAINT kb_relations_ibfk_1 FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  CONSTRAINT kb_relations_ibfk_2 FOREIGN KEY (source_id) REFERENCES kb_entities(id) ON DELETE CASCADE,
  CONSTRAINT kb_relations_ibfk_3 FOREIGN KEY (target_id) REFERENCES kb_entities(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── 嵌入模型配置 ─────────────────────────────────────────────────────────
CREATE TABLE embedding_model_configs (
  id            INT           NOT NULL AUTO_INCREMENT,
  user_id       INT           NOT NULL,
  name          VARCHAR(200)  NOT NULL,
  provider      VARCHAR(50)   NOT NULL,
  model_name    VARCHAR(200)  NOT NULL,
  api_base_url  VARCHAR(500)  NULL,
  api_key       TEXT          NULL,
  dimension     INT           NOT NULL,
  is_active     TINYINT(1)    NOT NULL DEFAULT 0,
  is_default    TINYINT(1)    NOT NULL DEFAULT 0,
  description   TEXT          NULL,
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX ix_embedding_model_configs_user_id (user_id),
  CONSTRAINT embedding_model_configs_ibfk_1 FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── OCR 配置 ─────────────────────────────────────────────────────────────
CREATE TABLE ocr_configs (
  id            INT           NOT NULL AUTO_INCREMENT,
  user_id       INT           NOT NULL,
  name          VARCHAR(200)  NOT NULL,
  provider      VARCHAR(50)   NOT NULL DEFAULT 'custom',
  api_base_url  VARCHAR(500)  NULL,
  api_key       TEXT          NULL,
  language      VARCHAR(50)   NOT NULL DEFAULT 'ch',
  is_active     TINYINT(1)    NOT NULL DEFAULT 0,
  description   TEXT          NULL,
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX ix_ocr_configs_user_id (user_id),
  CONSTRAINT ocr_configs_ibfk_1 FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── Alembic 版本号 ───────────────────────────────────────────────────────
CREATE TABLE alembic_version (
  version_num VARCHAR(32) NOT NULL,
  PRIMARY KEY (version_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO alembic_version (version_num) VALUES ('c853a95e4e86');
