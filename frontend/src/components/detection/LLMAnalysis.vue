<script setup lang="ts">
import { useDetectionStore } from '@/stores/detection'

const detectionStore = useDetectionStore()
</script>

<template>
  <div class="p-3">
    <div v-if="!detectionStore.llmAnalysis" class="text-center text-gray-400 py-8 text-sm">
      无LLM分析结果
    </div>
    <div v-else class="space-y-4">
      <!-- Summary -->
      <div v-if="detectionStore.llmAnalysis.summary">
        <h4 class="text-xs font-semibold text-gray-500 mb-1">摘要</h4>
        <p class="text-sm text-gray-700">{{ detectionStore.llmAnalysis.summary }}</p>
      </div>

      <!-- Objects detected -->
      <div v-if="detectionStore.llmAnalysis.objects_detected?.length">
        <h4 class="text-xs font-semibold text-gray-500 mb-1">检测到的对象</h4>
        <div class="flex flex-wrap gap-1">
          <el-tag v-for="obj in detectionStore.llmAnalysis.objects_detected" :key="obj" size="small" type="primary">
            {{ obj }}
          </el-tag>
        </div>
      </div>

      <!-- Detailed Analysis -->
      <div v-if="detectionStore.llmAnalysis.detailed_analysis">
        <h4 class="text-xs font-semibold text-gray-500 mb-1">详细分析</h4>
        <p class="text-sm text-gray-700 whitespace-pre-wrap">{{ detectionStore.llmAnalysis.detailed_analysis }}</p>
      </div>

      <!-- Region Analyses -->
      <div v-if="detectionStore.llmAnalysis.region_analyses?.length">
        <h4 class="text-xs font-semibold text-gray-500 mb-1">区域分析</h4>
        <div class="space-y-2">
          <div
            v-for="(region, idx) in detectionStore.llmAnalysis.region_analyses"
            :key="idx"
            class="bg-gray-50 rounded p-2"
          >
            <div class="text-xs font-medium text-gray-600">{{ region.object }}</div>
            <div class="text-xs text-gray-500 mt-1">{{ region.description }}</div>
          </div>
        </div>
      </div>

      <!-- Processing time -->
      <div class="text-xs text-gray-400 pt-2 border-t">
        处理耗时：{{ detectionStore.processingTime.toFixed(0) }}ms
      </div>
    </div>
  </div>
</template>
