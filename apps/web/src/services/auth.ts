import { apiError, safeFetch } from './http';
import { getRefreshToken } from '../utils/auth';
/**
 * 认证服务API
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: {
    id: string;
    username: string;
    display_name: string;
    roles: string[];
    student_id?: string;
  };
}

export interface RefreshTokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in: number;
}

export interface UserInfoResponse {
  user_id: string;
  username: string;
  display_name: string;
  school_id: string;
  roles: string[];
  student?: {
    id: string;
    name: string;
    student_no: string;
    grade: string;
    class_name: string;
  };
}

/**
 * 登录
 */
export const loginApi = async (data: LoginRequest): Promise<LoginResponse> => {
  const response = await safeFetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw await apiError(response, '登录失败');
  }

  return response.json();
};

/**
 * 刷新token
 */
export const refreshTokenApi = async (refreshToken: string, signal?: AbortSignal): Promise<RefreshTokenResponse> => {
  const response = await safeFetch(`${API_BASE_URL}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
    signal,
  });

  if (!response.ok) {
    throw await apiError(response, '登录已过期，请重新登录');
  }

  return response.json();
};

/**
 * 获取当前用户信息
 */
export const getCurrentUserApi = async (token: string): Promise<UserInfoResponse> => {
  const response = await safeFetch(`${API_BASE_URL}/auth/me`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw await apiError(response, '获取用户信息失败');
  }

  return response.json();
};

/**
 * 登出
 */
export const logoutApi = async (token: string | null, refreshToken: string | null = getRefreshToken()): Promise<void> => {
  const headers = new Headers({ 'Content-Type': 'application/json' });
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await safeFetch(`${API_BASE_URL}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
    headers,
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) throw await apiError(response, '退出登录失败，请重试');
};
