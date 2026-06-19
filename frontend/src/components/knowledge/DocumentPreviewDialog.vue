<script setup lang="ts">
import type { DocPreviewResponse } from '@/types/knowledge_base'

defineProps<{
  visible: boolean
  loading: boolean
  data: DocPreviewResponse | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="data ? data.filename : '文档预览'"
    width="720px"
    top="5vh"
    @update:model-value="(v: boolean) => !v && emit('close')"
  >
    <div v-if="loading" class="text-center py-8 text-gray-400">
      <el-icon class="is-loading" :size="20"><Refresh /></el-icon>
      <p class="mt-2 text-sm">加载中...</p>
    </div>
    <div v-else-if="!data" class="text-center py-8 text-gray-400">暂无数据</div>
    <div v-else class="space-y-4">
      <div class="flex items-center gap-3 text-sm text-gray-500">
        <span>类型: {{ data.file_type }}</span>
        <span>{{ data.file_size }} bytes</span>
        <el-tag :type="data.status === 'completed' ? 'success' : 'info'" size="small" effect="plain">
          {{ data.status === 'completed' ? '已处理' : data.status === 'processing' ? '处理中' : '等待处理' }}
        </el-tag>
      </div>
      <div class="bg-gray-50 rounded-lg p-4 whitespace-pre-wrap text-sm text-gray-700 leading-relaxed max-h-[500px] overflow-y-auto font-mono">
        {{ data.content_preview }}
      </div>
      <div v-if="data.content_preview.length >= 5000" class="text-xs text-gray-400 text-center">
        <el-tag size="small" effect="plain" type="warning">仅显示前 5000 字符</el-tag>
      </div>
    </div>
    <template #footer>
      <el-button @click="emit('close')">关闭</el-button>
    </template>
  </el-dialog>
</template>
