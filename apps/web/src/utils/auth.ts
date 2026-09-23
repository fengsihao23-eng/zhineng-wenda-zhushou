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
let sessionRevision = 0;
let sessionController = new AbortController();
const listeners = new Set<() => void>();

function rotateSession(): void {
  const previous = sessionController;
  sessionController = new AbortController();
  sessionRevision += 1;
  previous.abort();
}

export const getAuthSignal = (): AbortSignal => sessionController.signal;
export const getAuthScope = (): string => `${sessionRevision}:${getAuthIdentity()}`;
export const subscribeAuth = (listener: () => void): (() => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};

function notifyAuthChanged(): void {
  listeners.forEach(listener => listener());
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
  must_change_password?: boolean;
  account_type?: string;
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
  rotateSession();
  accessToken = null;
  getSessionStorage()?.removeItem(REFRESH_TOKEN_KEY);
  getSessionStorage()?.removeItem(USER_INFO_KEY);
  // Remove tokens written by versions that used persistent localStorage.
  removeLegacyPersistentAuth();
  const storage = getSessionStorage();
  if (storage) {
    for (let index = storage.length - 1; index >= 0; index -= 1) {
      const key = storage.key(index);
      if (key?.startsWith('stream_cursor:') || key?.startsWith('roster-active-batch:') || key?.startsWith('school-workbench-tab:')) storage.removeItem(key);
    }
  }
  notifyAuthChanged();
};

/**
 * 保存用户信息
 */
export const setUserInfo = (userInfo: UserInfo): void => {
  const previous = getAuthIdentity();
  const previousPermissions = JSON.stringify([getUserInfo()?.school_id, getUserInfo()?.roles]);
  getSessionStorage()?.setItem(USER_INFO_KEY, JSON.stringify(userInfo));
  if (previous !== getAuthIdentity() || previousPermissions !== JSON.stringify([userInfo.school_id, userInfo.roles])) rotateSession();
  notifyAuthChanged();
};

/** Publish login credentials and identity together so observers never see a half-login. */
export const setAuthSession = (token: string, refreshToken: string, userInfo: UserInfo): void => {
  rotateSession();
  accessToken = token;
  getSessionStorage()?.setItem(REFRESH_TOKEN_KEY, refreshToken);
  getSessionStorage()?.setItem(USER_INFO_KEY, JSON.stringify(userInfo));
  notifyAuthChanged();
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

/**
 * 返回当前登录身份标识，用于隔离 TanStack Query 缓存。
 * 同一浏览器标签页切换到另一个账号时，查询键必须随身份变化。
 */
export const getAuthIdentity = (): string => {
  const user = getUserInfo();
  if (!user) return 'anonymous';
  return `${user.user_id}:${user.student?.id || 'no-student'}`;
};

export { AUTH_CHANGED_EVENT };
