import client from './client'
import type { ApiResponse } from '@/types/api'
import type { DetectionResult } from '@/types/detection'

export const detectionApi = {
  detectImage(file: File, mode: string, modelId?: number | null, llmConfigId?: number | null) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('mode', mode)
    if (modelId) formData.append('model_id', String(modelId))
    if (llmConfigId) formData.append('llm_config_id', String(llmConfigId))
    return client.post<ApiResponse<DetectionResult>>('/api/detection/image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },
}
