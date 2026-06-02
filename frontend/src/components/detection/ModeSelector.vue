<script setup lang="ts">
import { useDetectionStore } from '@/stores/detection'
import type { DetectionMode } from '@/types/detection'
import { Aim, MagicStick, Link } from '@element-plus/icons-vue'

const detectionStore = useDetectionStore()

const modes: { value: DetectionMode; label: string; icon: any }[] = [
  { value: 'yolo_only', label: 'YOLO检测', icon: Aim },
  { value: 'llm_only', label: 'LLM分析', icon: MagicStick },
  { value: 'collaborative', label: '协同模式', icon: Link },
]

function selectMode(mode: DetectionMode) {
  detectionStore.setMode(mode)
}
</script>

<template>
  <div class="flex gap-1 bg-gray-100 rounded-lg p-1">
    <button
      v-for="m in modes"
      :key="m.value"
      @click="selectMode(m.value)"
      class="flex-1 flex flex-col items-center gap-0.5 py-2 px-3 rounded-md text-xs transition-all duration-200"
      :class="detectionStore.currentMode === m.value
        ? 'bg-white text-blue-600 shadow-sm'
        : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'"
    >
      <el-icon :size="18"><component :is="m.icon" /></el-icon>
      <span class="font-medium">{{ m.label }}</span>
    </button>
  </div>
</template>
