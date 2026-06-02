/** Generic API response wrapper. */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** Paginated list response. */
export interface PaginatedData<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

/** Bounding box data. */
export interface BBox {
  x1: number
  y1: number
  x2: number
  y2: number
  confidence: number
  class_name: string
  class_id: number
}

/** LLM analysis result. */
export interface LLMAnalysis {
  summary: string
  objects_detected: string[]
  detailed_analysis: string
  region_analyses: RegionAnalysis[]
}

/** Single region analysis. */
export interface RegionAnalysis {
  object: string
  description: string
}

/** Detection result. */
export interface DetectionResult {
  id: number
  mode: string
  source_type: string
  source_filename: string
  bboxes: BBox[]
  llm_analysis: LLMAnalysis | null
  thumbnail_path: string | null
  processing_time_ms: number
  created_at: string
}
