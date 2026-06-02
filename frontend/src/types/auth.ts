/** Login request. */
export interface LoginRequest {
  username: string
  password: string
}

/** Register request. */
export interface RegisterRequest {
  username: string
  email: string
  password: string
}

/** Token response. */
export interface TokenData {
  access_token: string
  token_type: string
}

/** Public user profile. */
export interface UserProfile {
  id: number
  username: string
  email: string
  created_at: string
  updated_at: string
}
