"""Pydantic schemas for knowledge base API."""

from datetime import datetime
from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    embedding_model: str = "default"


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None


class KnowledgeBaseResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: str | None
    status: str
    document_count: int
    chunk_count: int
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, kb) -> "KnowledgeBaseResponse":
        return cls(
            id=kb.id,
            user_id=kb.user_id,
            name=kb.name,
            description=kb.description,
            status=kb.status,
            document_count=kb.document_count,
            chunk_count=kb.chunk_count,
            created_at=kb.created_at.isoformat() if kb.created_at else "",
            updated_at=kb.updated_at.isoformat() if kb.updated_at else "",
        )


class KBDocumentResponse(BaseModel):
    id: int
    knowledge_base_id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    error_message: str | None
    chunk_count: int
    created_at: str

    @classmethod
    def from_model(cls, doc) -> "KBDocumentResponse":
        return cls(
            id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            filename=doc.filename,
            file_type=doc.file_type,
            file_size=doc.file_size,
            status=doc.status,
            error_message=doc.error_message,
            chunk_count=doc.chunk_count,
            created_at=doc.created_at.isoformat() if doc.created_at else "",
        )


class RAGQueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    kb_ids: list[int] = Field(..., min_length=1)
    llm_config_id: int | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class RAGSearchResult(BaseModel):
    chunk_id: str
    content: str
    distance: float
    document_filename: str
    knowledge_base_id: int
    highlights: list[str] = []


# ===== P1-1: RAG Chat Sessions =====

class RAGSessionCreate(BaseModel):
    """Request to create a new RAG chat session."""
    title: str | None = None


class RAGSessionResponse(BaseModel):
    """RAG chat session metadata."""
    session_id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


class RAGHistorySaveRequest(BaseModel):
    """Request to save RAG chat history."""
    session_id: str
    messages: list[dict]  # list of {role, content, reasoning?}


# ===== P1-2: Pagination =====

class PaginatedDocResponse(BaseModel):
    """Paginated document list response."""
    items: list[KBDocumentResponse]
    total: int
    page: int
    page_size: int


# ===== P1-3: KB Stats =====

class KBStatsResponse(BaseModel):
    """Knowledge base detailed statistics."""
    kb_id: int
    total_documents: int
    total_chunks: int
    total_tokens: int
    avg_chunks_per_doc: float
    avg_tokens_per_chunk: float
    status_breakdown: dict  # {"completed": N, "processing": N, "pending": N, "failed": N}
    file_type_breakdown: dict  # {".pdf": N, ".docx": N, ...}
    total_size_bytes: int
    last_updated: str


# ===== P1-4: Reindex =====

class ReindexStatusResponse(BaseModel):
    """Reindex operation progress status."""
    kb_id: int
    status: str  # "idle" | "running" | "completed" | "cancelled" | "failed"
    total_documents: int
    processed_documents: int
    progress_pct: float
    current_document: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


# ===== P2-1: Document Preview =====

class DocPreviewResponse(BaseModel):
    """Document content preview with chunk metadata."""
    doc_id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    content_preview: str  # first 500 lines of original content
    chunks: list[dict]  # [{"index": 0, "content_preview": "...", "token_count": N}]


# ===== P2-2: Batch Delete =====

class BatchDeleteRequest(BaseModel):
    """Request to batch delete documents."""
    doc_ids: list[int] = Field(..., min_length=1, max_length=100)


class BatchDeleteResponse(BaseModel):
    """Result of batch delete operation."""
    deleted_count: int
    failed_doc_ids: list[int]


# ===== P2-3: Import/Export =====

class ImportResultResponse(BaseModel):
    """Result of knowledge base import operation."""
    imported_documents: int
    imported_chunks: int
    errors: list[str] = []


class ImportProgressResponse(BaseModel):
    """Import operation progress status."""
    kb_id: int
    status: str  # "running" | "completed" | "failed"
    progress_pct: float
    processed_documents: int
    total_documents: int
    processed_chunks: int
    total_chunks: int
    current_step: str  # human-readable description of the current step
    error_message: str | None = None
