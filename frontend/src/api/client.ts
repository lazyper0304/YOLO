import axios, { type AxiosInstance, type AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

const client: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/',
  timeout: 60000,
})

// Request interceptor: attach JWT token
client.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor: handle errors
client.interceptors.response.use(
  (response) => {
    const data = response.data
    if (data.code !== 0 && data.code !== undefined) {
      const msg = data.message || 'Request failed'
      ElMessage.error(msg)
      return Promise.reject(new Error(msg))
    }
    return response
  },
  (error: AxiosError<{ detail?: string; message?: string }>) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      ElMessage.error('登录已过期，请重新登录')
      window.location.href = '/login'
      return Promise.reject(error)
    }
    if (error.response?.status === 500) {
      ElMessage.error('服务器内部错误')
    }
    const detail = error.response?.data?.detail || error.response?.data?.message || error.message
    if (detail && error.response?.status !== 401) {
      ElMessage.error(detail)
    }
    return Promise.reject(error)
  }
)

export default client
