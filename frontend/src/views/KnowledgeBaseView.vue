<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledge_base'
import { LayoutShell } from '@/components'
import { Plus, Upload, Delete, Refresh, Folder, Document, View, Download, Search, MoreFilled, EditPen, Clock } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { knowledgeBaseApi } from '@/api/knowledge_base'
import KnowledgeGraphPanel from '@/components/knowledge/KnowledgeGraphPanel.vue'
import KBSidebar from '@/components/knowledge/KBSidebar.vue'
import KBDocumentTable from '@/components/knowledge/KBDocumentTable.vue'
import DocumentPreviewDialog from '@/components/knowledge/DocumentPreviewDialog.vue'
import type { KnowledgeBase, KBDocument, DocPreviewResponse, DocProgress } from '@/types/knowledge_base'

const store = useKnowledgeBaseStore()

const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const createForm = ref({ name: '', description: '' })
const editForm = ref({ name: '', description: '' })
const editingKB = ref<KnowledgeBase | null>(null)
const kbSearchText = ref('')

const filteredKBs = computed(() => {
  if (!kbSearchText.value.trim()) return store.knowledgeBases
  const q = kbSearchText.value.toLowerCase()
  return store.knowledgeBases.filter(kb =>
    kb.name.toLowerCase().includes(q) ||
    (kb.description || '').toLowerCase().includes(q)
  )
})

// ─── Document Preview ─────────────────────────────────────────────
const showPreviewDialog = ref(false)
const previewData = ref<DocPreviewResponse | null>(null)
const previewLoading = ref(false)

// ─── Batch Delete ──────────────────────────────────────────────────
const selectedDocIds = ref<KBDocument[]>([])

function handleSelectionChange(selection: KBDocument[]) {
  selectedDocIds.value = selection
}

async function handleBatchDelete() {
  if (!store.currentKB || selectedDocIds.value.length === 0) return
  const count = selectedDocIds.value.length
  await ElMessageBox.confirm(
    `确定要删除选中的 ${count} 个文档吗？此操作不可恢复。`,
    '批量删除确认',
    { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
  )
  const docIds = selectedDocIds.value.map(d => d.id)
  await store.batchDeleteDocuments(store.currentKB.id, docIds)
  selectedDocIds.value = []
}

// ─── Export ────────────────────────────────────────────────────────
const isExporting = ref(false)

async function handleExport() {
  if (!store.currentKB) return
  isExporting.value = true
  try { await store.exportKB(store.currentKB.id) }
  finally { isExporting.value = false }
}

// ─── Import ────────────────────────────────────────────────────────
const importFileInput = ref<HTMLInputElement | null>(null)
const isImporting = ref(false)

function triggerImport() {
  importFileInput.value?.click()
}

async function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !store.currentKB) return
  if (!file.name.endsWith('.zip')) {
    ElMessageBox.alert('请选择 .zip 格式的文件', '文件格式错误')
    return
  }
  isImporting.value = true
  try { await store.importKB(store.currentKB.id, file) }
  finally { isImporting.value = false; if (input) input.value = '' }
}

function importStatusLabel(status: string) {
  const map: Record<string, string> = { idle: '空闲', running: '运行中', completed: '已完成', failed: '失败' }
  return map[status] || status
}

onMounted(() => { store.fetchKnowledgeBases() })
onUnmounted(() => { store.stopPolling() })

watch(() => store.currentKB, (newKB, oldKB) => {
  if (oldKB) store.stopPolling()
  if (newKB) store.startPolling(newKB.id)
})

function handlePageChange(page: number) {
  if (store.currentKB) store.fetchDocuments(store.currentKB.id, page)
}
function handlePageSizeChange(size: number) {
  if (store.currentKB) store.fetchDocuments(store.currentKB.id, 1, size)
}

async function handleCreate() {
  if (!createForm.value.name.trim()) return
  await store.createKnowledgeBase(createForm.value)
  showCreateDialog.value = false
  createForm.value = { name: '', description: '' }
}

function openEditDialog(kb: KnowledgeBase) {
  editingKB.value = kb
  editForm.value = { name: kb.name, description: kb.description || '' }
  showEditDialog.value = true
}

async function handleEdit() {
  if (!editingKB.value || !editForm.value.name.trim()) return
  await store.updateKnowledgeBase(editingKB.value.id, editForm.value)
  showEditDialog.value = false
}

async function handleDelete(kb: KnowledgeBase) {
  await ElMessageBox.confirm(`确定删除知识库「${kb.name}」？所有文档将被永久删除。`, '确认删除', {
    confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
  })
  await store.deleteKnowledgeBase(kb.id)
}

function selectKB(kb: KnowledgeBase) {
  store.setCurrentKB(kb)
  store.fetchDocuments(kb.id)
}

// ─── 上传文档（单个或批量） ─────────────────────────────────────
const showBatchUploadDialog = ref(false)
const batchUploadFiles = ref<File[]>([])
const batchUploadProgress = ref<string[]>([])
const isBatchUploading = ref(false)
const batchFileInputRef = ref<HTMLInputElement | null>(null)

function openBatchUpload() {
  batchUploadFiles.value = []
  batchUploadProgress.value = []
  showBatchUploadDialog.value = true
}

function onBatchFilesSelected(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files) return
  batchUploadFiles.value = Array.from(input.files)
}

async function startBatchUpload() {
  if (!store.currentKB || batchUploadFiles.value.length === 0) return
  isBatchUploading.value = true
  batchUploadProgress.value = []
  let success = 0
  let failed = 0
  for (let i = 0; i < batchUploadFiles.value.length; i++) {
    const file = batchUploadFiles.value[i]
    try {
      await store.uploadDocument(store.currentKB.id, file)
      batchUploadProgress.value.push(`✅ ${file.name} 上传成功`)
      success++
    } catch {
      batchUploadProgress.value.push(`❌ ${file.name} 上传失败`)
      failed++
    }
  }
  isBatchUploading.value = false
  ElMessage.success(`批量上传完成：成功 ${success} 个，失败 ${failed} 个`)
  if (failed === 0) {
    showBatchUploadDialog.value = false
  }
}

async function handleDeleteDoc(docId: number) {
  if (!store.currentKB) return
  await ElMessageBox.confirm('确定删除此文档？', '确认删除', {
    confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
  })
  await store.deleteDocument(store.currentKB.id, docId)
}

async function handleReprocess(docId: number) {
  if (!store.currentKB) return
  await store.reprocessDocument(store.currentKB.id, docId)
}

async function handlePreview(doc: KBDocument) {
  if (!store.currentKB) return
  previewLoading.value = true; showPreviewDialog.value = true; previewData.value = null
  try {
    const res = await knowledgeBaseApi.getDocumentPreview(store.currentKB.id, doc.id)
    previewData.value = res.data.data
  } catch (e: any) {
    ElMessageBox.alert(e.response?.data?.message || '获取文档预览失败', '预览失败')
    showPreviewDialog.value = false
  } finally { previewLoading.value = false }
}

async function handleReindex() {
  if (!store.currentKB) return
  await ElMessageBox.confirm(
    '重建索引将重新解析并嵌入知识库中所有非图片文档，这可能需要较长时间。是否继续？',
    '确认重建索引',
    { confirmButtonText: '开始', cancelButtonText: '取消', type: 'warning' }
  )
  await store.triggerReindex(store.currentKB.id)
}

function handleCancelReindex() {
  if (!store.currentKB) return
  store.cancelReindex(store.currentKB.id)
}

function reindexStatusLabel(status: string) {
  const map: Record<string, string> = { idle: '空闲', running: '运行中', completed: '已完成', cancelled: '已取消', failed: '失败' }
  return map[status] || status
}

function statusTagType(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'processing') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = { pending: '等待处理', processing: '处理中', completed: '已完成', failed: '处理失败' }
  return map[status] || status
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function fileTypeIcon(type: string) {
  if (type === '.pdf') return '📄'
  if (type === '.docx') return '📝'
  if (type === '.md') return '📋'
  if (type === '.txt') return '📃'
  if (['.jpg', '.jpeg', '.png', '.webp', '.bmp'].includes(type)) return '🖼️'
  return '📃'
}
</script>

<template>
  <LayoutShell>
    <div class="p-6">
      <!-- Header -->
      <div class="flex items-center justify-between mb-5">
        <div>
          <h2 class="text-xl font-bold text-gray-800">知识库管理</h2>
          <p class="text-sm text-gray-400 mt-0.5">管理知识库、文档及检索索引</p>
        </div>
        <el-button type="primary" :icon="Plus" size="default" @click="showCreateDialog = true">
          创建知识库
        </el-button>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-4 gap-5">
        <!-- Left: KB Sidebar -->
        <div class="lg:col-span-1">
          <KBSidebar v-model:search-text="kbSearchText" @edit="openEditDialog" @delete="handleDelete" />
        </div>

        <!-- Right: Document Area -->
        <div class="lg:col-span-3">
          <!-- Empty State -->
          <div v-if="!store.currentKB" class="bg-white rounded-lg shadow-sm border border-gray-100 p-16 text-center">
            <div class="w-16 h-16 bg-blue-50 rounded-full flex items-center justify-center mx-auto mb-4">
              <Folder :size="28" class="text-blue-400" />
            </div>
            <p class="text-gray-500 font-medium">选择一个知识库开始管理</p>
            <p class="text-sm text-gray-400 mt-1">从左侧列表选择，或创建新的知识库</p>
          </div>

          <!-- Active KB -->
          <div v-else class="bg-white rounded-lg shadow-sm border border-gray-100">
            <!-- KB Header -->
            <div class="px-4 py-3 border-b bg-gray-50/50">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                  <h3 class="text-base font-semibold text-gray-800">{{ store.currentKB.name }}</h3>
                  <div class="flex items-center gap-1.5">
                    <span class="inline-flex items-center gap-1 text-xs text-gray-500 bg-white rounded-md px-2 py-0.5 border">
                      <Document :size="12" /> {{ store.currentKB.document_count }}
                    </span>
                    <span class="inline-flex items-center gap-1 text-xs text-gray-500 bg-white rounded-md px-2 py-0.5 border">
                      片段 {{ store.currentKB.chunk_count }}
                    </span>
                  </div>
                </div>
                <div class="flex items-center gap-2">
                  <el-button type="primary" size="small" :icon="Upload" @click="openBatchUpload">上传文档</el-button>
                  <el-button size="small" :icon="EditPen" @click="openEditDialog(store.currentKB!)">编辑</el-button>
                  <el-popconfirm title="确定删除此知识库？所有文档将被永久删除。" confirm-button-text="删除" cancel-button-text="取消"
                    @confirm="handleDelete(store.currentKB!)">
                    <template #reference>
                      <el-button size="small" type="danger" plain :icon="Delete">删除</el-button>
                    </template>
                  </el-popconfirm>
                  <!-- More actions dropdown -->
                  <el-dropdown trigger="click">
                    <el-button size="small">更多 <el-icon class="el-icon--right"><MoreFilled /></el-icon></el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item :icon="Download" @click="handleExport">导出知识库</el-dropdown-item>
                        <el-dropdown-item :icon="Upload" @click="triggerImport">导入知识库</el-dropdown-item>
                        <el-dropdown-item divided :icon="Refresh" @click="handleReindex">重建索引</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </div>
              <p v-if="store.currentKB.description" class="text-xs text-gray-400 mt-1.5 ml-0.5">
                {{ store.currentKB.description }}
              </p>
            </div>

            <!-- Loading -->
            <div v-if="store.isLoading && store.documents.length === 0" class="p-10 text-center">
              <el-icon class="is-loading text-gray-400" :size="24"><Refresh /></el-icon>
            </div>

            <!-- Empty Documents -->
            <div v-else-if="store.documents.length === 0" class="p-12 text-center">
              <div class="w-14 h-14 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
                <Document :size="24" class="text-gray-300" />
              </div>
              <p class="text-gray-500 font-medium">暂无文档</p>
              <p class="text-sm text-gray-400 mt-1">点击上方「上传文档」按钮添加文件</p>
              <p class="text-xs text-gray-300 mt-2">支持 .txt, .md, .pdf, .docx 及图片 (.jpg, .png, .webp, .bmp)</p>
            </div>

            <!-- Document Table -->
            <template v-else>
              <!-- Batch actions bar -->
              <div v-if="selectedDocIds.length > 0" class="px-4 py-1.5 bg-red-50 border-b border-red-100 flex items-center gap-2">
                <span class="text-xs text-red-600">已选 {{ selectedDocIds.length }} 项</span>
                <el-button size="small" type="danger" plain :icon="Delete" @click="handleBatchDelete">批量删除</el-button>
              </div>

              <KBDocumentTable
                @preview="handlePreview"
                @reprocess="handleReprocess"
                @delete="handleDeleteDoc"
                @selection-change="handleSelectionChange"
              />

              <!-- Pagination -->
              <div v-if="store.totalDocs > store.pageSize" class="flex justify-center p-3 border-t">
                <el-pagination
                  v-model:current-page="store.currentPage"
                  v-model:page-size="store.pageSize"
                  :page-sizes="[10, 20, 50]"
                  :total="store.totalDocs"
                  layout="total, sizes, prev, pager, next"
                  size="small"
                  @current-change="handlePageChange"
                  @size-change="handlePageSizeChange"
                />
              </div>
            </template>
          </div>

          <!-- Knowledge Graph (always visible when KB selected) -->
          <KnowledgeGraphPanel v-if="store.currentKB" :kb-id="store.currentKB.id" />
        </div>
      </div>
    </div>

    <!-- Create Dialog -->
    <el-dialog v-model="showCreateDialog" title="创建知识库" width="420px">
      <el-form :model="createForm" label-width="60px">
        <el-form-item label="名称" required>
          <el-input v-model="createForm.name" placeholder="输入知识库名称" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="可选描述" maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- Edit Dialog -->
    <el-dialog v-model="showEditDialog" title="编辑知识库" width="420px">
      <el-form :model="editForm" label-width="60px">
        <el-form-item label="名称" required>
          <el-input v-model="editForm.name" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="handleEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- Reindex Dialog -->
    <el-dialog
      v-model="store.reindexDialogVisible"
      title="重建索引进度"
      width="460px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      @close="store.stopReindexPolling()"
    >
      <div v-if="store.reindexStatus" class="space-y-4">
        <div class="flex items-center justify-between text-sm">
          <span>
            状态：
            <el-tag :type="store.reindexStatus.status === 'running' ? 'warning' : store.reindexStatus.status === 'completed' ? 'success' : store.reindexStatus.status === 'failed' ? 'danger' : 'info'" size="small">
              {{ reindexStatusLabel(store.reindexStatus.status) }}
            </el-tag>
          </span>
          <span v-if="store.reindexStatus.total_documents > 0" class="text-gray-500">
            {{ store.reindexStatus.processed_documents }} / {{ store.reindexStatus.total_documents }} 文档
          </span>
        </div>
        <el-progress
          :percentage="store.reindexStatus.progress_pct"
          :status="store.reindexStatus.status === 'completed' ? 'success' : store.reindexStatus.status === 'failed' ? 'exception' : undefined"
          :stroke-width="18"
        />
        <div v-if="store.reindexStatus.current_document" class="text-sm text-gray-500">
          当前处理：{{ store.reindexStatus.current_document }}
        </div>
        <div v-if="store.reindexStatus.error_message" class="text-sm text-red-500">
          错误：{{ store.reindexStatus.error_message }}
        </div>
      </div>
      <template #footer>
        <el-button v-if="store.reindexStatus?.status === 'running'" type="danger" @click="handleCancelReindex">取消</el-button>
        <el-button v-else @click="store.reindexDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- Preview Dialog -->
    <DocumentPreviewDialog
      :visible="showPreviewDialog"
      :loading="previewLoading"
      :data="previewData"
      @close="showPreviewDialog = false"
    />

    <!-- Hidden import input -->
    <input ref="importFileInput" type="file" accept=".zip" style="display: none" @change="handleImportFile" />

    <!-- Import Progress Dialog -->
    <el-dialog
      v-model="store.importDialogVisible"
      title="导入进度"
      width="460px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      @close="store.stopImportPolling()"
    >
      <div v-if="store.importStatus" class="space-y-4">
        <div class="flex items-center justify-between text-sm">
          <span>
            状态：
            <el-tag :type="store.importStatus.status === 'running' ? 'warning' : store.importStatus.status === 'completed' ? 'success' : store.importStatus.status === 'failed' ? 'danger' : 'info'" size="small">
              {{ importStatusLabel(store.importStatus.status) }}
            </el-tag>
          </span>
          <span v-if="store.importStatus.total_documents > 0" class="text-gray-500">
            文档：{{ store.importStatus.processed_documents }} / {{ store.importStatus.total_documents }}
          </span>
        </div>
        <el-progress
          :percentage="store.importStatus.progress_pct"
          :status="store.importStatus.status === 'completed' ? 'success' : store.importStatus.status === 'failed' ? 'exception' : undefined"
          :stroke-width="18"
        />
        <div v-if="store.importStatus.current_step" class="text-sm text-gray-500">{{ store.importStatus.current_step }}</div>
        <div v-if="store.importStatus.error_message" class="text-sm text-red-500">错误：{{ store.importStatus.error_message }}</div>
      </div>
      <template #footer>
        <el-button v-if="store.importStatus?.status !== 'running'" @click="store.importDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 上传文档对话框 -->
    <el-dialog v-model="showBatchUploadDialog" title="上传文档" width="480px" top="15vh">
      <div class="space-y-4">
        <div class="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-400 transition-colors cursor-pointer"
          @click="batchFileInputRef?.click()">
          <el-icon :size="32" color="#9ca3af"><Upload /></el-icon>
          <p class="text-sm text-gray-400 mt-2">
            {{ batchUploadFiles.length > 0 ? `已选择 ${batchUploadFiles.length} 个文件` : '点击选择多个文件' }}
          </p>
          <p class="text-xs text-gray-300 mt-1">支持 .txt .md .pdf .docx .jpg .png 等格式，可单选或多选</p>
        </div>
        <input ref="batchFileInputRef" type="file" multiple hidden
          accept=".txt,.md,.pdf,.docx,.jpg,.jpeg,.png,.webp,.bmp"
          @change="onBatchFilesSelected" />
        <div v-if="batchUploadFiles.length > 0" class="text-xs text-gray-500 space-y-1 max-h-32 overflow-y-auto">
          <div v-for="(f, i) in batchUploadFiles" :key="i">{{ i + 1 }}. {{ f.name }}</div>
        </div>
        <div v-if="batchUploadProgress.length > 0" class="text-xs space-y-1 max-h-48 overflow-y-auto bg-gray-50 rounded p-2">
          <div v-for="(msg, i) in batchUploadProgress" :key="i" :class="msg.startsWith('✅') ? 'text-green-600' : 'text-red-500'">
            {{ msg }}
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showBatchUploadDialog = false" :disabled="isBatchUploading">取消</el-button>
        <el-button type="primary" :loading="isBatchUploading" :disabled="batchUploadFiles.length === 0"
          @click="startBatchUpload">
          开始上传 ({{ batchUploadFiles.length }})
        </el-button>
      </template>
    </el-dialog>
  </LayoutShell>
</template>
