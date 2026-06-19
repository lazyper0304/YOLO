import client from './client'

export interface OCRConfig {
  id: number
  name: string
  provider: string
  api_base_url: string | null
  language: string
  is_active: boolean
  description: string | null
  created_at: string | null
}

export interface OCRConfigForm {
  name: string
  provider?: string
  api_base_url?: string
  api_key?: string
  language?: string
  description?: string
}

const base = '/api/ocr-configs'

export const ocrConfigApi = {
  list() { return client.get(base) },
  create(form: OCRConfigForm) { return client.post(base, form) },
  update(id: number, form: Partial<OCRConfigForm & { is_active: boolean }>) {
    return client.put(`${base}/${id}`, form)
  },
  delete(id: number) { return client.delete(`${base}/${id}`) },
}
