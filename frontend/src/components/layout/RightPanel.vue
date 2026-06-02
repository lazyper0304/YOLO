<script setup lang="ts">
import { ref } from 'vue'
import { useDetectionStore } from '@/stores/detection'
import { useConfigStore } from '@/stores/config'
import { detectionApi } from '@/api/detection'
import { DataAnalysis } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import BBoxList from '@/components/detection/BBoxList.vue'
import LLMAnalysis from '@/components/detection/LLMAnalysis.vue'

const detectionStore = useDetectionStore()
const configStore = useConfigStore()

const activeTab = ref<'bbox' | 'llm'>('bbox')

async function handleDetect() {
  if (detectionStore.isProcessing) return
  if (!detectionStore.uploadedFile) {
    ElMessage.warning('请先上传图片')
    return
  }

  if (detectionStore.currentMode !== 'yolo_only') {
    const hasActiveLLM = configStore.activeLLMConfig || detectionStore.selectedLLMConfigId
    if (!hasActiveLLM) {
      ElMessage.warning('请先配置并选择 LLM 配置')
      return
    }
  }

  detectionStore.reset()
  detectionStore.isProcessing = true

  try {
    const res = await detectionApi.detectImage(
      detectionStore.uploadedFile,
      detectionStore.currentMode,
      detectionStore.selectedModelId,
      detectionStore.selectedLLMConfigId,
    )
    detectionStore.setDetectionResult(res.data.data)
    ElMessage.success(`检测完成，耗时 ${detectionStore.processingTime.toFixed(0)}ms`)
  } catch (err: any) {
    ElMessage.error(err?.message || '检测失败')
  } finally {
    detectionStore.isProcessing = false
  }
}
</script>

<template>
  <aside class="bg-white border-l border-gray-200 flex flex-col overflow-hidden flex-shrink-0">
    <!-- Action bar -->
    <div class="p-4 border-b border-gray-200">
      <el-button
        type="primary"
        size="large"
        class="w-full"
        :loading="detectionStore.isProcessing"
        :disabled="!detectionStore.uploadedFile || detectionStore.isProcessing"
        @click="handleDetect"
      >
        {{ detectionStore.isProcessing ? '检测中...' : '开始检测' }}
      </el-button>
    </div>

    <!-- Result tabs -->
    <div v-if="detectionStore.detectionResult" class="flex-1 min-h-0 flex flex-col overflow-hidden">
      <el-tabs v-model="activeTab" class="flex-1 min-h-0 flex flex-col">
        <el-tab-pane label="检测框" name="bbox">
          <div class="h-full overflow-y-auto p-2">
            <BBoxList />
          </div>
        </el-tab-pane>
        <el-tab-pane
          v-if="detectionStore.llmAnalysis"
          label="LLM分析"
          name="llm"
        >
          <div class="h-full overflow-y-auto">
            <LLMAnalysis />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- Empty state -->
    <div v-else class="flex-1 flex items-center justify-center p-4">
      <div class="text-center text-gray-400">
        <el-icon :size="48"><DataAnalysis /></el-icon>
        <p class="mt-2 text-sm">上传图片并点击检测</p>
        <p class="text-xs mt-1">结果将显示在这里</p>
      </div>
    </div>
  </aside>
</template>
