<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { Monitor, Setting, View, ChatDotRound, Collection } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const navItems = [
  { path: '/', label: '首页概览', icon: Monitor },
  { path: '/detection', label: '任务列表', icon: View },
  { path: '/models', label: '模型管理', icon: Setting },
  { path: '/knowledge-base', label: '知识库', icon: Collection },
  { path: '/chat', label: '智能助手', icon: ChatDotRound },
]

function navigate(path: string) { router.push(path) }

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <aside class="w-[180px] bg-white border-r border-gray-200 flex-shrink-0 flex flex-col select-none">
    <!-- Nav items -->
    <nav class="flex-1 px-2 py-2 space-y-0.5">
      <div
        v-for="item in navItems"
        :key="item.path"
        class="flex items-center gap-2.5 px-2.5 py-2 rounded-md cursor-pointer text-xs transition-all"
        :class="isActive(item.path)
          ? 'bg-blue-50 text-blue-600 font-medium'
          : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'"
        @click="navigate(item.path)"
      >
        <el-icon :size="16" class="flex-shrink-0"><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </div>
    </nav>
  </aside>
</template>
