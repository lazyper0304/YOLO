import client from './client'

export interface TaskItem {
  id: number
  mode: string
  task_name: string
  source_type: string
  source_path: string
  status: string
  result_json: Record<string, unknown> | null
  thumbnail_path: string | null
  frame_interval_seconds: number
  progress: number
  analysis_prompt?: string
  created_at: string
}

export interface TaskListData {
  items: TaskItem[]
  total: number
  page: number
  page_size: number
}

export async function fetchTasks(params?: { page?: number; page_size?: number; status?: string }): Promise<TaskListData> {
  const res = await client.get('/api/tasks', { params })
  return res.data.data
}

export async function getTask(id: number): Promise<TaskItem> {
  const res = await client.get(`/api/tasks/${id}`)
  return res.data.data
}

export async function createTask(form: FormData): Promise<{ id: number; status: string; estimated_frame_count?: number; estimated_duration_seconds?: number }> {
  const res = await client.post('/api/tasks', form)
  return res.data.data
}

export async function deleteTask(id: number): Promise<void> {
  await client.delete(`/api/tasks/${id}`)
}

export async function batchDeleteTasks(ids: number[]): Promise<void> {
  await client.post('/api/tasks/batch-delete', ids)
}

export async function pauseTask(id: number): Promise<{ status: string }> {
  const res = await client.post(`/api/tasks/${id}/pause`)
  return res.data.data
}

export async function resumeTask(id: number): Promise<{ status: string }> {
  const res = await client.post(`/api/tasks/${id}/resume`)
  return res.data.data
}
