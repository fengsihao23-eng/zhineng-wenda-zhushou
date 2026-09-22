import { describe, it, expect } from 'vitest'
import { CITY_ROLES, SCHOOL_ROLES, STUDENT_ROLES, TEACHER_ROLES, hasAnyRole, homePath } from './permissions'
import type { UserInfo } from './auth'
const user = (roles: string[]) => ({ user_id: 'synthetic', username: 'qa', display_name: 'QA', school_id: 'qa', roles } as UserInfo)
describe('role routes fail closed', () => {
  it('distinguishes all workspaces including QA and unknown roles', () => {
    for (const [role, allow, path] of [['STUDENT', STUDENT_ROLES, '/'], ['TEACHER', TEACHER_ROLES, '/teacher'], ['QA', SCHOOL_ROLES, '/admin'], ['SCHOOL_ADMIN', SCHOOL_ROLES, '/admin'], ['SUPER_ADMIN', CITY_ROLES, '/ops'], ['CITY_OPERATOR', CITY_ROLES, '/ops']] as const) {
      expect(hasAnyRole(user([role]), allow)).toBe(true)
      expect(homePath(user([role]))).toBe(path)
    }
    expect(hasAnyRole(null, STUDENT_ROLES)).toBe(false)
    expect(hasAnyRole(user([]), STUDENT_ROLES)).toBe(false)
    expect(hasAnyRole(user(['TEACHER']), SCHOOL_ROLES)).toBe(false)
    expect(hasAnyRole(user(['SCHOOL_ADMIN']), CITY_ROLES)).toBe(false)
  })
})
