import type { UserInfo } from './auth'

export const STUDENT_ROLES = ['STUDENT']
export const TEACHER_ROLES = ['TEACHER']
export const SCHOOL_ROLES = ['SCHOOL_ADMIN', 'QA']
export const CITY_ROLES = ['CITY_OPERATOR', 'SUPER_ADMIN']
export const ALL_ROLES = [...STUDENT_ROLES, ...TEACHER_ROLES, ...SCHOOL_ROLES, ...CITY_ROLES]

export function hasAnyRole(user: UserInfo | null, allowed: readonly string[]): boolean {
  return !!user?.roles?.some(role => allowed.includes(role.toUpperCase()))
}

export function homePath(user: UserInfo | null): string {
  if (hasAnyRole(user, CITY_ROLES)) return '/ops'
  if (hasAnyRole(user, SCHOOL_ROLES)) return '/admin'
  if (hasAnyRole(user, TEACHER_ROLES)) return '/teacher'
  return '/'
}
