import type { BBox, LLMAnalysis, DetectionResult } from './api'

/** Detection mode. */
export type DetectionMode = 'yolo_only' | 'llm_only' | 'collaborative'

/** Source type. */
export type SourceType = 'image' | 'video' | 'camera'

/** History record (list item). */
export interface HistoryItem {
  id: number
  source_type: SourceType
  source_path: string
  mode: DetectionMode
  thumbnail_path: string | null
  result_json: DetectionResult | null
  created_at: string
}

/** History detail. */
export interface HistoryDetail {
  id: number
  user_id: number
  source_type: SourceType
  source_path: string
  mode: DetectionMode
  yolo_model_id: number | null
  llm_config_id: number | null
  result_json: DetectionResult | null
  thumbnail_path: string | null
  created_at: string
}
