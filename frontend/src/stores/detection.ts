import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { BBox, LLMAnalysis, DetectionResult } from '@/types/api'
import type { DetectionMode } from '@/types/detection'

export const useDetectionStore = defineStore('detection', () => {
  const currentMode = ref<DetectionMode>('yolo_only')
  const selectedModelId = ref<number | null>(null)
  const selectedLLMConfigId = ref<number | null>(null)
  const uploadedFile = ref<File | null>(null)
  const uploadedFileUrl = ref<string | null>(null)
  const isProcessing = ref(false)
  const detectionResult = ref<DetectionResult | null>(null)
  const bboxes = ref<BBox[]>([])
  const llmAnalysis = ref<LLMAnalysis | null>(null)
  const processingTime = ref(0)
  const highlightedBBoxIndex = ref<number | null>(null)

  function setMode(mode: DetectionMode) {
    currentMode.value = mode
  }

  function setFile(file: File | null, url: string | null = null) {
    uploadedFile.value = file
    uploadedFileUrl.value = url
  }

  function setDetectionResult(result: DetectionResult) {
    detectionResult.value = result
    bboxes.value = result.bboxes || []
    llmAnalysis.value = result.llm_analysis || null
    processingTime.value = result.processing_time_ms || 0
  }

  function highlightBBox(index: number | null) {
    highlightedBBoxIndex.value = index
  }

  function reset() {
    detectionResult.value = null
    bboxes.value = []
    llmAnalysis.value = null
    processingTime.value = 0
    highlightedBBoxIndex.value = null
  }

  function resetAll() {
    reset()
    uploadedFile.value = null
    uploadedFileUrl.value = null
    currentMode.value = 'yolo_only'
    isProcessing.value = false
  }

  return {
    currentMode,
    selectedModelId,
    selectedLLMConfigId,
    uploadedFile,
    uploadedFileUrl,
    isProcessing,
    detectionResult,
    bboxes,
    llmAnalysis,
    processingTime,
    highlightedBBoxIndex,
    setMode,
    setFile,
    setDetectionResult,
    highlightBBox,
    reset,
    resetAll,
  }
})
