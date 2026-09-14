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
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(errorMessage(error, '登录失败'));
  }

  return response.json();
};

/**
 * 刷新token
 */
export const refreshTokenApi = async (refreshToken: string): Promise<RefreshTokenResponse> => {
  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(errorMessage(error, '刷新token失败'));
  }

  return response.json();
};

/**
 * 获取当前用户信息
 */
export const getCurrentUserApi = async (token: string): Promise<UserInfoResponse> => {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(errorMessage(error, '获取用户信息失败'));
  }

  return response.json();
};

/**
 * 登出
 */
export const logoutApi = async (token: string): Promise<void> => {
  await fetch(`${API_BASE_URL}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });
};

function errorMessage(payload: { error?: { message?: string }; detail?: string }, fallback: string): string {
  return payload?.error?.message || payload?.detail || fallback;
}
