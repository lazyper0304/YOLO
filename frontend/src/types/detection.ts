import type { BBox, LLMAnalysis } from './api'

/** Detection mode. */
export type DetectionMode = 'yolo_only' | 'llm_only' | 'collaborative'

/** Source type. */
export type SourceType = 'image' | 'video' | 'camera' | 'webcam'

/** Frame analysis result JSON. */
export interface FrameResult {
  frame_index: number
  time_seconds: number
  bboxes: BBox[]
  llm_analysis: LLMAnalysis | null
  thumbnail_path?: string
}

/** Task result JSON shape (video/camera). */
export interface DetectionResult {
  mode?: string
  source_type?: string
  bboxes?: BBox[]
  llm_analysis?: LLMAnalysis | null
  frame_count?: number
  total_frames?: number
  frames_completed?: number
  frames?: FrameResult[]
  detection_summary?: Array<{ class: string; count: number; avg_confidence?: number }>
  total_objects?: number
  video_path?: string
  error?: string
  analysis_prompt?: string
}

/** History record (list item). */
export interface HistoryItem {
  id: number
  source_type: SourceType
  source_path: string
  mode: DetectionMode
  thumbnail_path: string | null
  result_json: DetectionResult | null
  progress?: number
  frame_interval_seconds?: number
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
  progress?: number
  frame_interval_seconds?: number
  analysis_prompt?: string | null
  created_at: string
}
