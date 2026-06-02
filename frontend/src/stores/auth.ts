import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserProfile } from '@/types/auth'
import { authApi } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserProfile | null>(null)
  const token = ref<string>(localStorage.getItem('access_token') || '')

  const isAuthenticated = computed(() => !!token.value)
  const username = computed(() => user.value?.username || '')

  function setToken(t: string) {
    token.value = t
    localStorage.setItem('access_token', t)
  }

  function clearAuth() {
    token.value = ''
    user.value = null
    localStorage.removeItem('access_token')
  }

  async function login(username: string, password: string): Promise<void> {
    const res = await authApi.login({ username, password })
    setToken(res.data.data.access_token)
    await fetchUser()
  }

  async function register(username: string, email: string, password: string): Promise<void> {
    await authApi.register({ username, email, password })
  }

  async function fetchUser(): Promise<void> {
    if (!token.value) return
    try {
      const res = await authApi.getMe()
      user.value = res.data.data as UserProfile
    } catch {
      clearAuth()
    }
  }

  function logout() {
    clearAuth()
    window.location.href = '/login'
  }

  return {
    user,
    token,
    isAuthenticated,
    username,
    setToken,
    clearAuth,
    login,
    register,
    fetchUser,
    logout,
  }
})
