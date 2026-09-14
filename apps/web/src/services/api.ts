import { clearAuth, getRefreshToken, getToken, setToken } from '../utils/auth';
import { refreshTokenApi } from './auth';

export const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

let refreshInFlight: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  if (refreshInFlight) return refreshInFlight;
  const refreshToken = getRefreshToken();
  if (!refreshToken) throw new Error('登录已过期，请重新登录');

  refreshInFlight = refreshTokenApi(refreshToken)
    .then(refreshed => {
      // The API rotates refresh tokens. Always persist the returned value;
      // retaining the old token makes the next refresh fail by design.
      setToken(refreshed.access_token, refreshed.refresh_token || refreshToken);
      return refreshed.access_token;
    })
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!headers.has('Content-Type') && init.body) headers.set('Content-Type', 'application/json');
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, credentials: 'include' });
  if (response.status === 401 && !path.includes('/auth/')) {
    try {
      const accessToken = await refreshAccessToken();
      headers.set('Authorization', `Bearer ${accessToken}`);
      response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, credentials: 'include' });
    } catch {
      clearAuth();
    }
  }
  return response;
}

export async function apiError(response: Response, fallback: string): Promise<Error> {
  try {
    const payload = await response.json();
    return new Error(payload?.error?.message || payload?.detail || fallback);
  } catch {
    return new Error(fallback);
  }
}
