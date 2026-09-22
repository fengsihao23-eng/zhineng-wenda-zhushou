/**
 * 测试用户配置
 * 与 apps/api/scripts/init_test_data.py 保持一致
 */

export interface TestUser {
  username: string;
  password: string;
  displayName: string;
  role: 'student' | 'teacher' | 'school_admin' | 'city_operator';
  entitlement?: 'BASIC' | 'DIAGNOSIS';
}

export const TEST_USERS = {
  STUDENT_BASIC: {
    username: 'student_basic',
    password: 'password123',
    displayName: '张三',
    role: 'student' as const,
    entitlement: 'BASIC' as const,
  },

  STUDENT_DIAGNOSIS: {
    username: 'student_diagnosis',
    password: 'password123',
    displayName: '李四',
    role: 'student' as const,
    entitlement: 'DIAGNOSIS' as const,
  },

  TEACHER: {
    username: 'teacher_demo',
    password: 'password123',
    displayName: '教师工作台',
    role: 'teacher' as const,
  },

  SCHOOL_ADMIN: {
    username: 'school_admin_demo',
    password: 'password123',
    displayName: '学校管理台',
    role: 'school_admin' as const,
  },

  CITY_OPERATOR: {
    username: 'city_operator_demo',
    password: 'password123',
    displayName: '市级运营中心',
    role: 'city_operator' as const,
  },
} as const;

export type TestUserKey = keyof typeof TEST_USERS;
