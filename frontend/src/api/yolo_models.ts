import client from './client'
import type { ApiResponse } from '@/types/api'
import type { YOLOModelInfo } from '@/types/config'

export const yoloModelsApi = {
  list() {
    return client.get<ApiResponse<YOLOModelInfo[]>>('/api/yolo-models')
  },
  get(id: number) {
    return client.get<ApiResponse<YOLOModelInfo>>(`/api/yolo-models/${id}`)
  },
  upload(name: string, file: File) {
    const formData = new FormData()
    formData.append('name', name)
    formData.append('file', file)
    return client.post<ApiResponse<YOLOModelInfo>>('/api/yolo-models', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },
  update(id: number, data: { name?: string; is_active?: boolean }) {
    return client.put<ApiResponse<YOLOModelInfo>>(`/api/yolo-models/${id}`, data)
  },
  delete(id: number) {
    return client.delete<ApiResponse<null>>(`/api/yolo-models/${id}`)
  },
}
