<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { Monitor, VideoCamera, Setting, View, ChatDotRound } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const navItems = [
  { path: '/', label: '首页概览', icon: Monitor },
  { path: '/video', label: '视频源管理', icon: VideoCamera },
  { path: '/detection', label: '任务列表', icon: View },
  { path: '/models', label: '模型算法管理', icon: Setting },
  { path: '/chat', label: '智能问答', icon: ChatDotRound },
]

function navigate(path: string) {
  router.push(path)
}

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <aside class="bg-white border-r border-gray-200 overflow-y-auto flex-shrink-0">
    <nav class="p-2 space-y-1">
      <div
        v-for="item in navItems"
        :key="item.path"
        class="flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer text-sm transition-colors select-none"
        :class="isActive(item.path)
          ? 'bg-blue-50 text-blue-600 font-medium'
          : 'text-gray-600 hover:bg-gray-100'"
        @click="navigate(item.path)"
      >
        <el-icon :size="18" class="flex-shrink-0"><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </div>
    </nav>
  </aside>
</template>
