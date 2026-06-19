import client from './client'

export interface SystemStatus {
  cpu_percent: number
  memory_percent: number
  gpu?: {
    available: boolean
    utilization: number
    memory_used_mb: number
    memory_total_mb: number
    temperature?: number
  }
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const res = await client.get('/api/system/status')
  return res.data.data
}
