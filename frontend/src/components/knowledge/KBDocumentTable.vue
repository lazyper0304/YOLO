<script setup lang="ts">
import { useKnowledgeBaseStore } from '@/stores/knowledge_base'
import { Document, Delete, Refresh, View } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import type { KBDocument } from '@/types/knowledge_base'

const store = useKnowledgeBaseStore()

const emit = defineEmits<{
  (e: 'preview', doc: KBDocument): void
  (e: 'reprocess', docId: number): void
  (e: 'delete', docId: number): void
  (e: 'selection-change', selection: KBDocument[]): void
  (e: 'batch-delete', docIds: number[]): void
}>()

function statusLabel(status: string) {
  return { pending: '等待处理', processing: '处理中', completed: '已完成', failed: '处理失败' }[status] || status
}
function statusTagType(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'processing') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}
function formatFileSize(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
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
  <div>
    <div v-if="store.isLoading && store.documents.length === 0" class="p-10 text-center">
      <el-icon class="is-loading text-gray-400" :size="24"><Refresh /></el-icon>
    </div>

    <div v-else-if="store.documents.length === 0" class="p-12 text-center">
      <div class="w-14 h-14 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
        <Document :size="24" class="text-gray-300" />
      </div>
      <p class="text-gray-500 font-medium">暂无文档</p>
      <p class="text-sm text-gray-400 mt-1">点击上方「上传文档」按钮添加文件</p>
    </div>

    <template v-else>
      <el-table
        :data="store.documents"
        style="width: 100%"
        size="small"
        @selection-change="(sel: KBDocument[]) => emit('selection-change', sel)"
      >
        <el-table-column type="selection" width="40" />
        <el-table-column label="文件" min-width="200">
          <template #default="{ row }">
            <div class="flex items-center gap-2">
              <span class="text-base leading-none">{{ fileTypeIcon(row.file_type) }}</span>
              <div class="min-w-0">
                <div class="text-sm text-gray-700 truncate max-w-[200px]">{{ row.filename }}</div>
                <div class="text-[11px] text-gray-400">{{ formatFileSize(row.file_size) }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="片段" width="60" align="center" />
        <el-table-column label="操作" width="180" align="right">
          <template #default="{ row }">
            <div class="flex justify-end gap-1">
              <el-button link size="small" type="primary" :icon="View" @click="emit('preview', row)">预览</el-button>
              <el-button link size="small" :icon="Refresh" @click="emit('reprocess', row.id)">重处理</el-button>
              <el-popconfirm title="确定删除?" @confirm="emit('delete', row.id)">
                <template #reference>
                  <el-button link size="small" type="danger" :icon="Delete">删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </div>
</template>
