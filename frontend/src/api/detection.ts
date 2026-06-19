import client from './client'
import type { ApiResponse } from '@/types/api'
import type { DetectionResult, FrameAnalysisResult, GeneratedPrompt } from '@/types/api'

export const detectionApi = {
  detectImage(file: File, mode: string, modelId?: number | null, llmConfigId?: number | null, llmAnalysisScope?: string) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('mode', mode)
    if (modelId) formData.append('model_id', String(modelId))
    if (llmConfigId) formData.append('llm_config_id', String(llmConfigId))
    if (llmAnalysisScope) formData.append('llm_analysis_scope', llmAnalysisScope)
    return client.post<ApiResponse<DetectionResult>>('/api/detection/image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },

  /** Submit a camera frame for LLM analysis. */
  analyzeFrame(
    taskId: number,
    frameIndex: number,
    timeSeconds: number,
    frameBlob: Blob,
  ) {
    const form = new FormData()
    form.append('file', frameBlob, `frame_${frameIndex}.jpg`)
    form.append('frame_index', String(frameIndex))
    form.append('time_seconds', String(timeSeconds))
    return client.post<ApiResponse<FrameAnalysisResult>>(
      `/api/tasks/${taskId}/analyze-frame`,
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000,
      }
    )
  },

  /** Generate an analysis prompt via LLM conversation. */
  generatePrompt(requirement: string, llmConfigId?: number | null) {
    return client.post<ApiResponse<GeneratedPrompt>>(
      '/api/chat/generate-prompt',
      {
        requirement,
        llm_config_id: llmConfigId,
      },
      { params: { token: localStorage.getItem('access_token') || '' } }
    )
  },
}
