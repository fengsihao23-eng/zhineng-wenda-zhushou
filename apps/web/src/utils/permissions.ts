import type { UserInfo } from './auth'

export const STUDENT_ROLES = ['STUDENT']
export const TEACHER_ROLES = ['TEACHER']
export const SCHOOL_ROLES = ['SCHOOL_ADMIN', 'QA', 'SCHOOL_VIEWER']
export const CITY_ROLES = ['CITY_OPERATOR']
export const PLATFORM_ADMIN_ROLES = ['SUPER_ADMIN']
export const ALL_ROLES = [...STUDENT_ROLES, ...TEACHER_ROLES, ...SCHOOL_ROLES, ...CITY_ROLES, ...PLATFORM_ADMIN_ROLES, 'EXAM_ADMIN']

export function hasAnyRole(user: UserInfo | null, allowed: readonly string[]): boolean {
  return !!user?.roles?.some(role => allowed.includes(role.toUpperCase()))
}

export function homePath(user: UserInfo | null): string {
  if (hasAnyRole(user, PLATFORM_ADMIN_ROLES)) return '/ops/administrators'
  if (hasAnyRole(user, CITY_ROLES)) return '/ops'
  if (hasAnyRole(user, [...SCHOOL_ROLES, 'EXAM_ADMIN'])) return '/admin/school?tab=exam-management'
  if (hasAnyRole(user, TEACHER_ROLES)) return '/teacher'
  return '/'
}
