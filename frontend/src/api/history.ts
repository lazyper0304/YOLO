import client from './client'
import type { ApiResponse, PaginatedData } from '@/types/api'
import type { HistoryItem, HistoryDetail } from '@/types/detection'

export const historyApi = {
  list(params?: { page?: number; page_size?: number; mode?: string; source_type?: string }) {
    return client.get<ApiResponse<PaginatedData<HistoryItem>>>('/api/history', { params })
  },
  getDetail(id: number) {
    return client.get<ApiResponse<HistoryDetail>>(`/api/history/${id}`)
  },
}
