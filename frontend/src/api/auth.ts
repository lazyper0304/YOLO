import client from './client'
import type { LoginRequest, RegisterRequest, TokenData, UserProfile } from '@/types/auth'
import type { ApiResponse } from '@/types/api'

export const authApi = {
  login(data: LoginRequest) {
    return client.post<ApiResponse<TokenData>>('/api/auth/login', data)
  },
  register(data: RegisterRequest) {
    return client.post<ApiResponse<{ id: number; username: string }>>('/api/auth/register', data)
  },
  getMe() {
    return client.get<ApiResponse<UserProfile>>('/api/auth/me')
  },
}
