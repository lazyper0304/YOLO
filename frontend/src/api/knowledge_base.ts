import client from './client'
import type { ApiResponse } from '@/types/api'
import type {
  KnowledgeBase,
  KnowledgeBaseCreate,
  KnowledgeBaseUpdate,
  KBDocument,
  DocProgressMap,
  GraphData,
  RAGQueryRequest,
  RAGSearchResult,
  PaginatedDocResponse,
  KBStatsResponse,
  ReindexStatusResponse,
  DocPreviewResponse,
  BatchDeleteRequest,
  BatchDeleteResponse,
  ImportResultResponse,
  ImportProgressResponse,
  RAGSessionResponse,
  RAGSessionCreate,
  RAGHistorySaveRequest,
  HistoryMessage,
} from '@/types/knowledge_base'

export const knowledgeBaseApi = {
  // Knowledge Base CRUD
  list() {
    return client.get<ApiResponse<KnowledgeBase[]>>('/api/knowledge-bases')
  },

  create(data: KnowledgeBaseCreate) {
    return client.post<ApiResponse<KnowledgeBase>>('/api/knowledge-bases', data)
  },

  get(id: number) {
    return client.get<ApiResponse<KnowledgeBase>>(`/api/knowledge-bases/${id}`)
  },

  update(id: number, data: KnowledgeBaseUpdate) {
    return client.put<ApiResponse<KnowledgeBase>>(`/api/knowledge-bases/${id}`, data)
  },

  delete(id: number) {
    return client.delete<ApiResponse<null>>(`/api/knowledge-bases/${id}`)
  },

  // Document Management
  listDocuments(kbId: number, page: number = 1, pageSize: number = 20) {
    return client.get<ApiResponse<PaginatedDocResponse>>(
      `/api/knowledge-bases/${kbId}/documents`,
      { params: { page, page_size: pageSize } }
    )
  },

  uploadDocument(kbId: number, file: File) {
    const formData = new FormData()
    formData.append('file', file)
    return client.post<ApiResponse<KBDocument>>(
      `/api/knowledge-bases/${kbId}/documents`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
  },

  deleteDocument(kbId: number, docId: number) {
    return client.delete<ApiResponse<null>>(`/api/knowledge-bases/${kbId}/documents/${docId}`)
  },

  reprocessDocument(kbId: number, docId: number) {
    return client.post<ApiResponse<null>>(`/api/knowledge-bases/${kbId}/documents/${docId}/reprocess`)
  },

  // Redis progress tracking
  bulkProgress(kbId: number, docIds: number[]) {
    return client.get<ApiResponse<DocProgressMap>>(
      `/api/knowledge-bases/${kbId}/documents/progress`,
      { params: { doc_ids: docIds.join(',') } }
    )
  },

  // Search
  search(data: RAGQueryRequest) {
    return client.post<ApiResponse<RAGSearchResult[]>>('/api/knowledge-bases/search', data)
  },

  // ===== P1-3: KB Stats =====
  getKBStats(kbId: number) {
    return client.get<ApiResponse<KBStatsResponse>>(`/api/knowledge-bases/${kbId}/stats`)
  },

  // ===== P1-4: Reindex =====
  triggerReindex(kbId: number) {
    return client.post<ApiResponse<{ task_id: string; status: string }>>(`/api/knowledge-bases/${kbId}/reindex`)
  },

  getReindexStatus(kbId: number) {
    return client.get<ApiResponse<ReindexStatusResponse>>(`/api/knowledge-bases/${kbId}/reindex/status`)
  },

  cancelReindex(kbId: number) {
    return client.post<ApiResponse<null>>(`/api/knowledge-bases/${kbId}/reindex/cancel`)
  },

  // ===== P2-1: Document Preview =====
  getDocumentPreview(kbId: number, docId: number) {
    return client.get<ApiResponse<DocPreviewResponse>>(`/api/knowledge-bases/${kbId}/documents/${docId}/preview`)
  },

  // ===== P2-2: Batch Delete =====
  batchDeleteDocuments(kbId: number, docIds: number[]) {
    return client.post<ApiResponse<BatchDeleteResponse>>(
      `/api/knowledge-bases/${kbId}/documents/batch-delete`,
      { doc_ids: docIds } as BatchDeleteRequest
    )
  },

  // ===== P2-3: Import/Export =====
  exportKB(kbId: number) {
    return client.get(`/api/knowledge-bases/${kbId}/export`, { responseType: 'blob' })
  },

  importKB(kbId: number, zipFile: File) {
    const formData = new FormData()
    formData.append('file', zipFile)
    return client.post<ApiResponse<ImportResultResponse>>(
      `/api/knowledge-bases/${kbId}/import`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
  },

  getImportStatus(kbId: number) {
    return client.get<ApiResponse<ImportProgressResponse>>(`/api/knowledge-bases/${kbId}/import/status`)
  },

  // ===== P1-1: RAG Chat Sessions =====
  getRAGSessions(kbId: number) {
    return client.get<ApiResponse<RAGSessionResponse[]>>(`/api/knowledge-bases/${kbId}/rag-sessions`)
  },

  createRAGSession(kbId: number, title?: string) {
    return client.post<ApiResponse<RAGSessionResponse>>(
      `/api/knowledge-bases/${kbId}/rag-sessions`,
      { title } as RAGSessionCreate
    )
  },

  deleteRAGSession(kbId: number, sessionId: string) {
    return client.delete<ApiResponse<null>>(`/api/knowledge-bases/${kbId}/rag-sessions/${sessionId}`)
  },

  getRAGHistory(kbId: number, sessionId: string) {
    return client.get<ApiResponse<{ session_id: string; messages: HistoryMessage[] }>>(
      `/api/knowledge-bases/${kbId}/rag-sessions/${sessionId}/history`
    )
  },

  saveRAGHistory(kbId: number, sessionId: string, messages: HistoryMessage[]) {
    return client.post<ApiResponse<null>>(
      `/api/knowledge-bases/${kbId}/rag-sessions/${sessionId}/history`,
      { session_id: sessionId, messages } as RAGHistorySaveRequest
    )
  },

  clearRAGHistory(kbId: number, sessionId: string) {
    return client.delete<ApiResponse<null>>(`/api/knowledge-bases/${kbId}/rag-sessions/${sessionId}/history`)
  },

  // ===== Knowledge Graph =====
  getGraph(kbId: number) {
    return client.get<ApiResponse<GraphData>>(`/api/knowledge-bases/${kbId}/graph`)
  },

  extractGraph(kbId: number) {
    return client.post<ApiResponse<{ entities_added: number; relations_added: number }>>(
      `/api/knowledge-bases/${kbId}/graph/extract`
    )
  },

  getEntityChunks(kbId: number, entityId: number) {
    return client.get<ApiResponse<{ entity: string; chunks: any[] }>>(
      `/api/knowledge-bases/${kbId}/graph/entity/${entityId}/chunks`
    )
  },
}
