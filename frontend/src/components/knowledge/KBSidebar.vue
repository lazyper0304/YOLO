<script setup lang="ts">
import { computed } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledge_base'
import { Folder, Refresh, Search, EditPen, MoreFilled } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import type { KnowledgeBase } from '@/types/knowledge_base'

const store = useKnowledgeBaseStore()

const emit = defineEmits<{
  (e: 'edit', kb: KnowledgeBase): void
  (e: 'delete', kb: KnowledgeBase): void
  (e: 'update:searchText', val: string): void
}>()

const props = defineProps<{
  searchText: string
}>()

function onSearch(val: string) {
  emit('update:searchText', val)
}

const filteredKBs = computed(() => {
  if (!props.searchText.trim()) return store.knowledgeBases
  const q = props.searchText.toLowerCase()
  return store.knowledgeBases.filter(kb =>
    kb.name.toLowerCase().includes(q) ||
    (kb.description || '').toLowerCase().includes(q)
  )
})

function selectKB(kb: KnowledgeBase) {
  store.setCurrentKB(kb)
  store.fetchDocuments(kb.id)
}
</script>

<template>
  <div class="bg-white rounded-lg shadow-sm border border-gray-100">
    <div class="p-3 border-b">
      <div class="flex items-center gap-2 mb-2">
        <span class="text-xs font-semibold text-gray-500 uppercase tracking-wider">知识库列表</span>
        <span class="text-xs text-gray-400 bg-gray-100 rounded-full px-2 py-0.5">{{ store.knowledgeBases.length }}</span>
      </div>
      <el-input
        v-if="store.knowledgeBases.length > 3"
        :model-value="searchText"
        @update:model-value="onSearch"
        placeholder="搜索..."
        size="small"
        :prefix-icon="Search"
        clearable
      />
    </div>

    <div v-if="store.isLoading && store.knowledgeBases.length === 0" class="p-6 text-center">
      <el-icon class="is-loading text-gray-400" :size="20"><Refresh /></el-icon>
    </div>
    <div v-else-if="filteredKBs.length === 0 && store.knowledgeBases.length > 0" class="p-6 text-center text-gray-400 text-sm">
      无匹配的知识库
    </div>
    <div v-else-if="store.knowledgeBases.length === 0" class="p-6 text-center">
      <Folder :size="32" class="mx-auto mb-2 text-gray-200" />
      <p class="text-sm text-gray-400">暂无知识库</p>
      <p class="text-xs text-gray-300 mt-1">点击右上角创建</p>
    </div>
    <div v-else class="divide-y max-h-[calc(100vh-280px)] overflow-y-auto">
      <div
        v-for="kb in filteredKBs"
        :key="kb.id"
        class="px-3 py-2.5 cursor-pointer hover:bg-blue-50/50 transition-colors group"
        :class="{ 'bg-blue-50 border-l-[3px] border-l-blue-500': store.currentKB?.id === kb.id }"
        @click="selectKB(kb)"
      >
        <div class="flex items-start justify-between">
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-gray-700 truncate">{{ kb.name }}</div>
            <div class="flex items-center gap-2 mt-1 text-xs text-gray-400">
              <span>{{ kb.document_count }} 文档</span>
              <span>·</span>
              <span>{{ kb.chunk_count }} 片段</span>
            </div>
          </div>
          <el-dropdown trigger="click" class="opacity-0 group-hover:opacity-100 transition-opacity">
            <el-button link size="small" class="!p-0"><MoreFilled :size="14" class="text-gray-400" /></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item :icon="EditPen" @click.stop="emit('edit', kb)">编辑</el-dropdown-item>
                <el-dropdown-item divided @click.stop="emit('delete', kb)">
                  <span class="text-red-500">删除</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </div>
  </div>
</template>
