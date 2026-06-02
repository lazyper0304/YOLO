<script setup lang="ts">
import { useDetectionStore } from '@/stores/detection'

const detectionStore = useDetectionStore()

function handleClick(index: number) {
  if (detectionStore.highlightedBBoxIndex === index) {
    detectionStore.highlightBBox(null)
  } else {
    detectionStore.highlightBBox(index)
  }
}

const colors = ['#FF0000', '#00FF00', '#0000FF', '#FFFF00', '#FF00FF', '#00FFFF']
</script>

<template>
  <div class="p-3">
    <div v-if="detectionStore.bboxes.length === 0" class="text-center text-gray-400 py-8 text-sm">
      未检测到目标
    </div>
    <div v-else class="space-y-2">
      <div class="text-xs text-gray-400 mb-2">
        共 {{ detectionStore.bboxes.length }} 个目标（按置信度降序）
      </div>
      <div
        v-for="(bbox, index) in detectionStore.bboxes"
        :key="index"
        class="flex items-center gap-3 p-2 rounded cursor-pointer transition-colors hover:bg-gray-50"
        :class="{ 'bg-blue-50 ring-1 ring-blue-200': detectionStore.highlightedBBoxIndex === index }"
        @click="handleClick(index)"
      >
        <span
          class="w-3 h-3 rounded-full flex-shrink-0"
          :style="{ backgroundColor: colors[index % colors.length] }"
        />
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium truncate">{{ bbox.class_name }}</div>
          <div class="text-xs text-gray-400">
            [{{ bbox.x1.toFixed(0) }}, {{ bbox.y1.toFixed(0) }}, {{ bbox.x2.toFixed(0) }}, {{ bbox.y2.toFixed(0) }}]
          </div>
        </div>
        <el-tag size="small" type="success">
          {{ (bbox.confidence * 100).toFixed(1) }}%
        </el-tag>
      </div>
    </div>
  </div>
</template>
