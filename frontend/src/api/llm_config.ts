import client from './client'
import type { ApiResponse } from '@/types/api'
import type { LLMConfig, LLMConfigForm, LLMTestResult } from '@/types/config'

export const llmConfigApi = {
  list() {
    return client.get<ApiResponse<LLMConfig[]>>('/api/llm-configs')
  },
  create(data: LLMConfigForm) {
    return client.post<ApiResponse<LLMConfig>>('/api/llm-configs', data)
  },
  get(id: number) {
    return client.get<ApiResponse<LLMConfig>>(`/api/llm-configs/${id}`)
  },
  update(id: number, data: Partial<LLMConfigForm>) {
    return client.put<ApiResponse<LLMConfig>>(`/api/llm-configs/${id}`, data)
  },
  delete(id: number) {
    return client.delete<ApiResponse<null>>(`/api/llm-configs/${id}`)
  },
  test(id: number) {
    return client.post<ApiResponse<LLMTestResult>>(`/api/llm-configs/${id}/test`)
  },
}
