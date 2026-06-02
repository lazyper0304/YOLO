import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { LLMConfig, LLMConfigForm, LLMTestResult, YOLOModelInfo } from '@/types/config'
import { llmConfigApi } from '@/api/llm_config'
import { yoloModelsApi } from '@/api/yolo_models'

export const useConfigStore = defineStore('config', () => {
  const llmConfigs = ref<LLMConfig[]>([])
  const yoloModels = ref<YOLOModelInfo[]>([])
  const isLoadingLLM = ref(false)
  const isLoadingYOLO = ref(false)

  const activeLLMConfig = computed(() =>
    llmConfigs.value.find((c) => c.is_active) || null
  )
  const customModels = computed(() =>
    yoloModels.value.filter((m) => !m.is_builtin)
  )
  const builtinModels = computed(() =>
    yoloModels.value.filter((m) => m.is_builtin)
  )

  async function fetchLLMConfigs() {
    isLoadingLLM.value = true
    try {
      const res = await llmConfigApi.list()
      llmConfigs.value = res.data.data as LLMConfig[]
    } finally {
      isLoadingLLM.value = false
    }
  }

  async function createLLMConfig(form: LLMConfigForm) {
    const res = await llmConfigApi.create(form)
    await fetchLLMConfigs()
    return res.data.data
  }

  async function updateLLMConfig(id: number, form: Partial<LLMConfigForm>) {
    const res = await llmConfigApi.update(id, form)
    await fetchLLMConfigs()
    return res.data.data
  }

  async function deleteLLMConfig(id: number) {
    await llmConfigApi.delete(id)
    await fetchLLMConfigs()
  }

  async function testLLMConfig(id: number): Promise<LLMTestResult> {
    const res = await llmConfigApi.test(id)
    return res.data.data as LLMTestResult
  }

  async function fetchYOLOModels() {
    isLoadingYOLO.value = true
    try {
      const res = await yoloModelsApi.list()
      yoloModels.value = res.data.data as YOLOModelInfo[]
    } finally {
      isLoadingYOLO.value = false
    }
  }

  async function uploadYOLOModel(name: string, file: File) {
    const res = await yoloModelsApi.upload(name, file)
    await fetchYOLOModels()
    return res.data.data
  }

  async function deleteYOLOModel(id: number) {
    await yoloModelsApi.delete(id)
    await fetchYOLOModels()
  }

  async function setActiveLLMConfig(id: number) {
    await updateLLMConfig(id, { is_active: true })
  }

  return {
    llmConfigs,
    yoloModels,
    isLoadingLLM,
    isLoadingYOLO,
    activeLLMConfig,
    customModels,
    builtinModels,
    fetchLLMConfigs,
    createLLMConfig,
    updateLLMConfig,
    deleteLLMConfig,
    testLLMConfig,
    fetchYOLOModels,
    uploadYOLOModel,
    deleteYOLOModel,
    setActiveLLMConfig,
  }
})
