import { defineStore } from 'pinia'
import { ref } from 'vue'
import { knowledgeBaseApi } from '@/api/knowledge_base'
import type { KnowledgeBase, KBDocument, KnowledgeBaseCreate, ReindexStatusResponse, ImportProgressResponse, DocProgress, DocProgressMap } from '@/types/knowledge_base'
import { ElMessage } from 'element-plus'

export const useKnowledgeBaseStore = defineStore('knowledge_base', () => {
  const knowledgeBases = ref<KnowledgeBase[]>([])
  const currentKB = ref<KnowledgeBase | null>(null)
  const documents = ref<KBDocument[]>([])
  const isLoading = ref(false)
  const isUploading = ref(false)

  // Pagination state
  const currentPage = ref(1)
  const pageSize = ref(20)
  const totalDocs = ref(0)

  // Polling state
  const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)
  const pollingKBId = ref<number | null>(null)

  // Redis doc progress state
  const docProgress = ref<DocProgressMap>({})

  // Reindex state
  const reindexStatus = ref<ReindexStatusResponse | null>(null)
  const reindexPollTimer = ref<ReturnType<typeof setInterval> | null>(null)
  const reindexDialogVisible = ref(false)

  // Import progress state
  const importStatus = ref<ImportProgressResponse | null>(null)
  const importPollTimer = ref<ReturnType<typeof setInterval> | null>(null)
  const importDialogVisible = ref(false)

  async function fetchKnowledgeBases() {
    isLoading.value = true
    try {
      const res = await knowledgeBaseApi.list()
      knowledgeBases.value = res.data.data
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '获取知识库列表失败')
    } finally {
      isLoading.value = false
    }
  }

  async function createKnowledgeBase(data: KnowledgeBaseCreate) {
    try {
      const res = await knowledgeBaseApi.create(data)
      knowledgeBases.value.unshift(res.data.data)
      ElMessage.success('知识库创建成功')
      return res.data.data
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '创建知识库失败')
      throw e
    }
  }

  async function updateKnowledgeBase(id: number, data: { name?: string; description?: string }) {
    try {
      const res = await knowledgeBaseApi.update(id, data)
      const idx = knowledgeBases.value.findIndex(kb => kb.id === id)
      if (idx !== -1) {
        knowledgeBases.value[idx] = res.data.data
      }
      if (currentKB.value?.id === id) {
        currentKB.value = res.data.data
      }
      ElMessage.success('知识库更新成功')
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '更新知识库失败')
      throw e
    }
  }

  async function deleteKnowledgeBase(id: number) {
    try {
      await knowledgeBaseApi.delete(id)
      knowledgeBases.value = knowledgeBases.value.filter(kb => kb.id !== id)
      if (currentKB.value?.id === id) {
        currentKB.value = null
        documents.value = []
        stopPolling()
      }
      ElMessage.success('知识库已删除')
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '删除知识库失败')
      throw e
    }
  }

  async function fetchDocuments(kbId: number, page?: number, pageSizeVal?: number) {
    const p = page ?? currentPage.value
    const ps = pageSizeVal ?? pageSize.value
    isLoading.value = true
    try {
      const res = await knowledgeBaseApi.listDocuments(kbId, p, ps)
      documents.value = res.data.data.items
      totalDocs.value = res.data.data.total
      currentPage.value = res.data.data.page
      pageSize.value = res.data.data.page_size
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '获取文档列表失败')
    } finally {
      isLoading.value = false
    }
  }

  async function uploadDocument(kbId: number, file: File) {
    isUploading.value = true
    try {
      const res = await knowledgeBaseApi.uploadDocument(kbId, file)
      // After upload, refresh the current page to see the new doc
      await fetchDocuments(kbId)
      // Update KB document count
      const kb = knowledgeBases.value.find(k => k.id === kbId)
      if (kb) {
        kb.document_count++
      }
      if (currentKB.value?.id === kbId) {
        currentKB.value.document_count++
      }
      ElMessage.success('文档上传成功，正在处理中...')
      // Start polling if not already
      startPolling(kbId)
      return res.data.data
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '上传文档失败')
      throw e
    } finally {
      isUploading.value = false
    }
  }

  async function deleteDocument(kbId: number, docId: number) {
    try {
      await knowledgeBaseApi.deleteDocument(kbId, docId)
      const doc = documents.value.find(d => d.id === docId)
      documents.value = documents.value.filter(d => d.id !== docId)
      totalDocs.value = Math.max(0, totalDocs.value - 1)
      // Update KB counters
      const kb = knowledgeBases.value.find(k => k.id === kbId)
      if (kb && doc) {
        kb.document_count = Math.max(0, kb.document_count - 1)
        kb.chunk_count = Math.max(0, kb.chunk_count - (doc.chunk_count || 0))
      }
      ElMessage.success('文档已删除')
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '删除文档失败')
      throw e
    }
  }

  async function reprocessDocument(kbId: number, docId: number) {
    try {
      await knowledgeBaseApi.reprocessDocument(kbId, docId)
      // Update local status
      const doc = documents.value.find(d => d.id === docId)
      if (doc) {
        doc.status = 'pending'
        doc.error_message = null
      }
      // Start polling to track progress
      startPolling(kbId)
      ElMessage.success('文档重新处理中...')
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '重新处理失败')
      throw e
    }
  }

  // ─── Polling ───────────────────────────────────────────────

  function startPolling(kbId: number) {
    stopPolling()
    pollingKBId.value = kbId
    docProgress.value = {}
    pollTimer.value = setInterval(async () => {
      try {
        // 1. Fetch Redis progress for pending/processing docs
        const pendingIds = documents.value
          .filter(d => d.status === 'pending' || d.status === 'processing')
          .map(d => d.id)
        if (pendingIds.length > 0) {
          const res = await knowledgeBaseApi.bulkProgress(kbId, pendingIds)
          docProgress.value = res.data.data || {}
        }

        // 2. Refresh from MySQL to get final status changes
        await fetchDocuments(kbId)

        // 3. Stop polling when no more pending/processing
        const hasProcessing = documents.value.some(
          d => d.status === 'pending' || d.status === 'processing' || d.status === 'failed'
        )
        if (!hasProcessing && documents.value.length > 0) {
          docProgress.value = {}
          stopPolling()
          // Refresh KB list to update sidebar counts
          fetchKnowledgeBases()
        } else if (hasProcessing) {
          // Keep polling but slower if only failed docs remain
          const onlyFailed = documents.value.every(d => d.status !== 'pending' && d.status !== 'processing')
          if (onlyFailed) {
            stopPolling()
            docProgress.value = {}
            fetchKnowledgeBases()
          }
        }
      } catch {
        // Silently ignore
      }
    }, 3000)
  }

  function stopPolling() {
    if (pollTimer.value !== null) {
      clearInterval(pollTimer.value)
      pollTimer.value = null
    }
    pollingKBId.value = null
    docProgress.value = {}
  }

  // ─── Reindex ──────────────────────────────────────────────

  async function triggerReindex(kbId: number) {
    try {
      const res = await knowledgeBaseApi.triggerReindex(kbId)
      if (res.data.data?.status === 'started') {
        reindexStatus.value = {
          kb_id: kbId,
          status: 'running',
          total_documents: 0,
          processed_documents: 0,
          progress_pct: 0,
          current_document: null,
          error_message: null,
          started_at: null,
          finished_at: null,
        }
        reindexDialogVisible.value = true
        startReindexPolling(kbId)
        ElMessage.success('重建索引已启动')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '启动重建索引失败')
      throw e
    }
  }

  function startReindexPolling(kbId: number) {
    stopReindexPolling()
    reindexPollTimer.value = setInterval(async () => {
      try {
        const res = await knowledgeBaseApi.getReindexStatus(kbId)
        const status = res.data.data
        reindexStatus.value = status

        if (status.status === 'completed') {
          stopReindexPolling()
          ElMessage.success('重建索引已完成')
          // Refresh document list
          await fetchDocuments(kbId)
          // Auto-close dialog after short delay
          setTimeout(() => {
            reindexDialogVisible.value = false
          }, 1500)
        } else if (status.status === 'failed') {
          stopReindexPolling()
          ElMessage.error(status.error_message || '重建索引失败')
        } else if (status.status === 'cancelled') {
          stopReindexPolling()
          ElMessage.info('重建索引已取消')
          await fetchDocuments(kbId)
          setTimeout(() => {
            reindexDialogVisible.value = false
          }, 1500)
        } else if (status.status === 'idle') {
          stopReindexPolling()
          reindexDialogVisible.value = false
        }
      } catch {
        // Silently ignore poll errors
      }
    }, 3000)
  }

  function stopReindexPolling() {
    if (reindexPollTimer.value !== null) {
      clearInterval(reindexPollTimer.value)
      reindexPollTimer.value = null
    }
  }

  async function cancelReindex(kbId: number) {
    try {
      await knowledgeBaseApi.cancelReindex(kbId)
      ElMessage.success('取消请求已发送')
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '取消重建索引失败')
    }
  }

  // ─── Batch Delete ──────────────────────────────────────────

  async function batchDeleteDocuments(kbId: number, docIds: number[]) {
    try {
      const res = await knowledgeBaseApi.batchDeleteDocuments(kbId, docIds)
      const { deleted_count, failed_doc_ids } = res.data.data
      // Remove successfully deleted docs from local state
      const failedSet = new Set(failed_doc_ids)
      documents.value = documents.value.filter(d => !docIds.includes(d.id) || failedSet.has(d.id))
      totalDocs.value = Math.max(0, totalDocs.value - deleted_count)
      // Update KB counters
      const kb = knowledgeBases.value.find(k => k.id === kbId)
      if (kb) {
        kb.document_count = Math.max(0, kb.document_count - deleted_count)
        // Approximate chunk_count update — exact count comes from server refresh
        const deletedDocs = docIds.filter(id => !failed_doc_ids.includes(id))
        const totalChunks = documents.value
          .filter(d => deletedDocs.includes(d.id) && failedSet.has(d.id))
          .reduce((sum, d) => sum + (d.chunk_count || 0), 0)
        kb.chunk_count = Math.max(0, kb.chunk_count - totalChunks)
      }
      if (currentKB.value?.id === kbId) {
        currentKB.value.document_count = Math.max(0, currentKB.value.document_count - deleted_count)
      }
      if (failed_doc_ids.length > 0) {
        ElMessage.warning(`成功删除 ${deleted_count} 个文档，${failed_doc_ids.length} 个删除失败`)
      } else {
        ElMessage.success(`成功删除 ${deleted_count} 个文档`)
      }
      // Refresh doc list from server
      await fetchDocuments(kbId)
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '批量删除失败')
      throw e
    }
  }

  // ─── Export ─────────────────────────────────────────────────

  async function exportKB(kbId: number) {
    try {
      const res = await knowledgeBaseApi.exportKB(kbId)
      // Extract filename from Content-Disposition header
      const disposition = res.headers['content-disposition']
      let filename = 'knowledge_base_export.zip'
      if (disposition) {
        const match = disposition.match(/filename\*=UTF-8''(.+)/)
        if (match) {
          filename = decodeURIComponent(match[1])
        } else {
          const simpleMatch = disposition.match(/filename="?(.+?)"?$/ )
          if (simpleMatch) {
            filename = simpleMatch[1]
          }
        }
      }
      // Trigger browser download
      const blob = new Blob([res.data], { type: 'application/zip' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      ElMessage.success('知识库导出成功')
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '导出知识库失败')
      throw e
    }
  }

  // ─── Import ─────────────────────────────────────────────────

  async function importKB(kbId: number, file: File) {
    try {
      const res = await knowledgeBaseApi.importKB(kbId, file)
      if (res.data.data?.status === 'started') {
        importStatus.value = {
          kb_id: kbId,
          status: 'running',
          progress_pct: 0,
          processed_documents: 0,
          total_documents: 0,
          processed_chunks: 0,
          total_chunks: 0,
          current_step: '准备导入...',
          error_message: null,
        }
        importDialogVisible.value = true
        startImportPolling(kbId)
        ElMessage.success('导入已启动')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.message || '导入知识库失败')
      throw e
    }
  }

  function startImportPolling(kbId: number) {
    stopImportPolling()
    importPollTimer.value = setInterval(async () => {
      try {
        const res = await knowledgeBaseApi.getImportStatus(kbId)
        const status = res.data.data
        importStatus.value = status

        if (status.status === 'completed') {
          stopImportPolling()
          ElMessage.success('导入完成')
          await fetchDocuments(kbId)
          setTimeout(() => {
            importDialogVisible.value = false
          }, 2000)
        } else if (status.status === 'failed') {
          stopImportPolling()
          ElMessage.error(status.error_message || '导入失败')
        }
      } catch {
        // Silently ignore poll errors
      }
    }, 2000)
  }

  function stopImportPolling() {
    if (importPollTimer.value !== null) {
      clearInterval(importPollTimer.value)
      importPollTimer.value = null
    }
  }

  function setCurrentKB(kb: KnowledgeBase | null) {
    currentKB.value = kb
    // Reset pagination when switching KB
    if (kb) {
      currentPage.value = 1
      totalDocs.value = 0
    }
  }

  return {
    knowledgeBases,
    currentKB,
    documents,
    docProgress,
    isLoading,
    isUploading,
    currentPage,
    pageSize,
    totalDocs,
    pollingKBId,
    reindexStatus,
    reindexDialogVisible,
    importStatus,
    importDialogVisible,
    fetchKnowledgeBases,
    createKnowledgeBase,
    updateKnowledgeBase,
    deleteKnowledgeBase,
    fetchDocuments,
    uploadDocument,
    deleteDocument,
    reprocessDocument,
    startPolling,
    stopPolling,
    triggerReindex,
    startReindexPolling,
    stopReindexPolling,
    cancelReindex,
    batchDeleteDocuments,
    exportKB,
    importKB,
    startImportPolling,
    stopImportPolling,
    setCurrentKB,
  }
})
