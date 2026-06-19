import client from './client'

export interface DashboardData {
  today_detections: number
  total_detections: number
  mode_breakdown: { yolo_only: number; llm_only: number; collaborative: number }
  yolo_models: number
  llm_configs: number
  recent_detections: { id: number; mode: string; source_type: string; created_at: string }[]
}

export interface DailyStats {
  dates: string[]
  counts: number[]
}

export interface PieData {
  series: { name: string; value: number }[]
}

export async function fetchDashboardStats(): Promise<DashboardData> {
  const res = await client.get('/api/dashboard/stats')
  return res.data.data
}

export async function fetchDailyStats(days = 14): Promise<DailyStats> {
  const res = await client.get(`/api/dashboard/daily?days=${days}`)
  return res.data.data
}

export async function fetchModePie(): Promise<PieData> {
  const res = await client.get('/api/dashboard/mode-pie')
  return res.data.data
}

export async function fetchModelCalls(): Promise<PieData> {
  const res = await client.get('/api/dashboard/model-calls')
  return res.data.data
}
