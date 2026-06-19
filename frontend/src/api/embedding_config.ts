import client from './client'
import type { ApiResponse } from '@/types/api'
import type { EmbeddingConfig, EmbeddingConfigForm, EmbeddingTestResult } from '@/types/config'

export const embeddingConfigApi = {
  list() {
    return client.get<ApiResponse<EmbeddingConfig[]>>('/api/embedding-configs')
  },

  create(data: EmbeddingConfigForm) {
    return client.post<ApiResponse<EmbeddingConfig>>('/api/embedding-configs', data)
  },

  get(id: number) {
    return client.get<ApiResponse<EmbeddingConfig>>(`/api/embedding-configs/${id}`)
  },

  update(id: number, data: Partial<EmbeddingConfigForm>) {
    return client.put<ApiResponse<EmbeddingConfig>>(`/api/embedding-configs/${id}`, data)
  },

  delete(id: number) {
    return client.delete<ApiResponse<null>>(`/api/embedding-configs/${id}`)
  },

  test(id: number) {
    return client.post<ApiResponse<EmbeddingTestResult>>(`/api/embedding-configs/${id}/test`)
  },
}
