/** LLM provider type. */
export type LLMProvider = 'openai' | 'claude' | 'generic' | 'ollama'

/** LLM configuration. */
export interface LLMConfig {
  id: number
  user_id: number
  name: string
  api_base_url: string
  api_key: string
  model_name: string
  provider: LLMProvider
  is_active: boolean
}

/** LLM config create/update form. */
export interface LLMConfigForm {
  name: string
  api_base_url: string
  api_key: string
  model_name: string
  provider: LLMProvider
  is_active: boolean
}

/** LLM connection test result. */
export interface LLMTestResult {
  success: boolean
  message: string
  response_time_ms: number
}

/** YOLO model. */
export interface YOLOModelInfo {
  id: number
  user_id: number
  name: string
  file_path: string
  model_type: string
  is_builtin: boolean
  file_size: number
  is_active: boolean
  uploaded_at: string
}
