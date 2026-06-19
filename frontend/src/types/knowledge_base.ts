export interface KnowledgeBase {
  id: number
  user_id: number
  name: string
  description: string | null
  status: string
  document_count: number
  chunk_count: number
  created_at: string
  updated_at: string
}

export interface KBDocument {
  id: number
  knowledge_base_id: number
  filename: string
  file_type: string
  file_size: number
  status: string
  error_message: string | null
  chunk_count: number
  created_at: string
}

/** Redis progress snapshot for a processing document */
export interface DocProgress {
  doc_id: number
  step: string
  pct: number
  message: string
  chunk_count?: number
}

export interface DocProgressMap {
  [docId: string]: DocProgress
}

/** Knowledge Graph */
export interface GraphNode {
  id: number
  name: string
  type: string
  description: string | null
}

export interface GraphEdge {
  source: number
  target: number
  type: string
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface KnowledgeBaseCreate {
  name: string
  description?: string
}

export interface KnowledgeBaseUpdate {
  name?: string
  description?: string
  status?: string
}

export interface RAGQueryRequest {
  question: string
  kb_ids: number[]
  llm_config_id?: number | null
  top_k?: number
}

export interface RAGSearchResult {
  chunk_id: string
  content: string
  distance: number
  document_filename: string
  knowledge_base_id: number
  highlights: string[]
}

// ===== P1-1: RAG Chat Sessions =====

export interface HistoryMessage {
  role: string // "user" | "assistant"
  content: string
  reasoning?: string | null
}

export interface RAGSessionCreate {
  title?: string | null
}

export interface RAGSessionResponse {
  session_id: string
  title: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface RAGHistorySaveRequest {
  session_id: string
  messages: HistoryMessage[]
}

// ===== P1-2: Pagination =====

export interface PaginatedDocResponse {
  items: KBDocument[]
  total: number
  page: number
  page_size: number
}

// ===== P1-3: KB Stats =====

export interface KBStatsResponse {
  kb_id: number
  total_documents: number
  total_chunks: number
  total_tokens: number
  avg_chunks_per_doc: number
  avg_tokens_per_chunk: number
  status_breakdown: Record<string, number>
  file_type_breakdown: Record<string, number>
  total_size_bytes: number
  last_updated: string
}

// ===== P1-4: Reindex =====

export interface ReindexStatusResponse {
  kb_id: number
  status: string // "idle" | "running" | "completed" | "cancelled" | "failed"
  total_documents: number
  processed_documents: number
  progress_pct: number
  current_document: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
}

// ===== P2-1: Document Preview =====

export interface DocPreviewResponse {
  doc_id: number
  filename: string
  file_type: string
  file_size: number
  status: string
  content_preview: string
  file_url: string | null  // file download URL (PDF/images)
  chunks: Array<{ index: number; content_preview: string; token_count: number }>
}

// ===== P2-2: Batch Delete =====

export interface BatchDeleteRequest {
  doc_ids: number[]
}

export interface BatchDeleteResponse {
  deleted_count: number
  failed_doc_ids: number[]
}

// ===== P2-3: Import/Export =====

export interface ImportResultResponse {
  imported_documents: number
  imported_chunks: number
  errors: string[]
}

export interface ImportProgressResponse {
  kb_id: number
  status: string // "idle" | "running" | "completed" | "failed"
  progress_pct: number
  processed_documents: number
  total_documents: number
  processed_chunks: number
  total_chunks: number
  current_step: string
  error_message: string | null
}
