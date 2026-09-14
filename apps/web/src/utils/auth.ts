/**
 * 认证工具函数
 */

const REFRESH_TOKEN_KEY = 'refresh_token';
const USER_INFO_KEY = 'user_info';
const LEGACY_TOKEN_KEY = 'auth_token';
const AUTH_CHANGED_EVENT = 'auth:changed';

// Access tokens live only in memory.  The refresh token is scoped to the
// browser tab so a copied token does not survive a full browser restart.
let accessToken: string | null = null;

function notifyAuthChanged(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
  }
}

function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function removeLegacyPersistentAuth(): void {
  try {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(LEGACY_TOKEN_KEY);
      window.localStorage.removeItem(USER_INFO_KEY);
    }
  } catch {
    // Ignore storage errors in restricted browser contexts.
  }
}

removeLegacyPersistentAuth();

export interface UserInfo {
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
 * 保存token
 */
export const setToken = (accessToken: string, refreshToken: string): void => {
  // Keep the access token out of persistent browser storage.  The parameter
  // name is retained for API compatibility with existing callers.
  setAccessToken(accessToken);
  getSessionStorage()?.setItem(REFRESH_TOKEN_KEY, refreshToken);
  notifyAuthChanged();
};

export const setAccessToken = (token: string): void => {
  accessToken = token;
};

/**
 * 获取访问token
 */
export const getToken = (): string | null => {
  return accessToken;
};

/**
 * 获取刷新token
 */
export const getRefreshToken = (): string | null => {
  return getSessionStorage()?.getItem(REFRESH_TOKEN_KEY) || null;
};

/**
 * 清除所有认证信息
 */
export const clearAuth = (): void => {
  accessToken = null;
  getSessionStorage()?.removeItem(REFRESH_TOKEN_KEY);
  getSessionStorage()?.removeItem(USER_INFO_KEY);
  // Remove tokens written by versions that used persistent localStorage.
  removeLegacyPersistentAuth();
  notifyAuthChanged();
};

/**
 * 保存用户信息
 */
export const setUserInfo = (userInfo: UserInfo): void => {
  getSessionStorage()?.setItem(USER_INFO_KEY, JSON.stringify(userInfo));
};

/**
 * 获取用户信息
 */
export const getUserInfo = (): UserInfo | null => {
  const data = getSessionStorage()?.getItem(USER_INFO_KEY);
  if (!data) return null;
  try {
    return JSON.parse(data) as UserInfo;
  } catch {
    return null;
  }
};

/**
 * 检查是否已认证
 */
export const isAuthenticated = (): boolean => {
  // A tab with a refresh token can silently obtain a fresh access token.
  return !!getToken() || !!getRefreshToken();
};

export { AUTH_CHANGED_EVENT };
