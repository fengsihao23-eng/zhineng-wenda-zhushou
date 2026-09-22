import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { clearAuth, getAuthIdentity, setUserInfo, type UserInfo } from './auth';

function makeStorage() {
  const map = new Map<string, string>();
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => { map.set(key, value); },
    removeItem: (key: string) => { map.delete(key); },
    clear: () => { map.clear(); },
    key: (index: number) => Array.from(map.keys())[index] ?? null,
    get length() { return map.size; },
  };
}

function userWithStudent(userId: string, studentId: string): UserInfo {
  return {
    user_id: userId,
    username: `user-${userId}`,
    display_name: `User ${userId}`,
    school_id: 'school-1',
    roles: ['STUDENT'],
    student: {
      id: studentId,
      name: `Student ${studentId}`,
      student_no: studentId,
      grade: '高一',
      class_name: '1班',
    },
  };
}

const originalWindow = globalThis.window;

beforeEach(() => {
  const storage = makeStorage();
  // auth.ts 在浏览器上下文中通过 window.sessionStorage 读取身份。
  (globalThis as unknown as { window: unknown }).window = {
    sessionStorage: storage,
    localStorage: storage,
    dispatchEvent: () => true,
  };
  (globalThis as unknown as { sessionStorage: unknown }).sessionStorage = storage;
});

afterEach(() => {
  clearAuth();
  (globalThis as unknown as { window: unknown }).window = originalWindow;
});

describe('getAuthIdentity', () => {
  it('在未登录时返回 anonymous', () => {
    expect(getAuthIdentity()).toBe('anonymous');
  });

  it('身份键包含用户与学生 ID，账号切换后会变化', () => {
    setUserInfo(userWithStudent('u1', 'st1'));
    expect(getAuthIdentity()).toBe('u1:st1');

    setUserInfo(userWithStudent('u2', 'st2'));
    expect(getAuthIdentity()).toBe('u2:st2');
  });

  it('同一用户切换学生绑定时身份键也会变化', () => {
    setUserInfo(userWithStudent('u1', 'st1'));
    const before = getAuthIdentity();
    setUserInfo(userWithStudent('u1', 'st2'));
    expect(getAuthIdentity()).not.toBe(before);
  });
});
