import { describe, expect, it } from 'vitest'
import { EMPTY_TEACHER_FILTERS, matchesTeacher, permissionDraft, permissionIssues, teacherFilterOptions, type PermissionTeacher } from './teacher-permissions'

const teacher: PermissionTeacher = {
  id: 'teacher-1', platform_id: '10001985', name: '同名教师', account: 'teacher-a', fields: {},
  duties: ['TEACHER', 'HOMEROOM_TEACHER'], role_labels: ['任课教师', '班主任'],
  filter_scopes: [
    { role: 'TEACHER', grade: '11', class_number: '01班', subject: '物理' },
    { role: 'TEACHER', grade: '高中一年级', class_number: '2', subject: '数学' },
    { role: 'HOMEROOM_TEACHER', grade: '高中一年级', class_number: '9', subject: '' },
  ], scope_classes: [], scope_grades: [], default_warnings: [],
  recommendation: { teacher_id: 'teacher-1', score_types: ['student'], score_subjects: ['math'], diagnosis_types: [], diagnosis_subjects: [], essay_types: [], range_type: 'class', grades: [], classes: ['高中一年级 / 2'] },
}
const people = [{ id: 'student-1', grade: '高中一年级', class_number: '2' }, { id: 'student-2', grade: '高中一年级', class_number: '9' }]
const subjects = [{ subject_id: 'math', name: '数学', student_ids: ['student-1'] }, { subject_id: 'chinese', name: '语文', student_ids: ['student-2'] }]

describe('teacher permission filters and recipient binding', () => {
  it('offers actual teacher responsibilities outside the selected exam and normalizes numeric classes', () => {
    const options = teacherFilterOptions([teacher], EMPTY_TEACHER_FILTERS)
    expect(options.grades).toEqual(['高中一年级', '高中二年级'])
    expect(options.classes).toEqual(['高中一年级 / 2', '高中一年级 / 9', '高中二年级 / 1'])
    expect(options.subjects).toContain('物理')
    expect(teacherFilterOptions([teacher], { ...EMPTY_TEACHER_FILTERS, grade: '高中二年级' }).classes).toEqual(['高中二年级 / 1'])
  })
  it('requires grade, class, subject and duty to match one responsibility', () => {
    expect(matchesTeacher(teacher, { ...EMPTY_TEACHER_FILTERS, grade: '高中二年级', classroom: '高中二年级 / 1', subject: '物理', duty: 'TEACHER' })).toBe(true)
    expect(matchesTeacher(teacher, { ...EMPTY_TEACHER_FILTERS, grade: '高中一年级', subject: '物理' })).toBe(false)
    expect(matchesTeacher(teacher, { ...EMPTY_TEACHER_FILTERS, classroom: '高中一年级 / 2', duty: 'HOMEROOM_TEACHER' })).toBe(false)
    expect(matchesTeacher(teacher, { ...EMPTY_TEACHER_FILTERS, classroom: '高中一年级 / 9', subject: '数学' })).toBe(false)
    expect(matchesTeacher(teacher, { ...EMPTY_TEACHER_FILTERS, search: ' TEACHER-A ' })).toBe(true)
    expect(matchesTeacher(teacher, { ...EMPTY_TEACHER_FILTERS, search: '10001985' })).toBe(true)
  })
  it('keeps same-name teacher drafts independent and always uses the recipient ID', () => {
    const first = permissionDraft(teacher)
    const other = { ...teacher, id: 'teacher-2', platform_id: '10001986' }
    const second = permissionDraft(other, { ...first, teacher_id: 'wrong-person' })
    second.classes.push('高中一年级 / 9')
    second.score_subjects.push('chinese')
    expect(first.classes).toEqual(['高中一年级 / 2'])
    expect(teacher.recommendation.score_subjects).toEqual(['math'])
    expect(second.teacher_id).toBe('teacher-2')
  })
  it('rejects a requested subject with no students in the chosen range', () => {
    const draft = permissionDraft(teacher)
    expect(permissionIssues(draft, people, subjects, ['math'])).toEqual([])
    draft.diagnosis_types = ['student']; draft.diagnosis_subjects = ['chinese']
    expect(permissionIssues(draft, people, subjects, ['math'])).toContain('语文在当前学生范围内没有参试学生')
  })
  it('rejects stale ranges, missing imports and essay languages outside the exam', () => {
    const draft = permissionDraft(teacher)
    draft.classes = ['高中三年级 / 1']; draft.essay_types = ['english']
    const issues = permissionIssues(draft, people, subjects, [])
    expect(issues).toContain('学生范围没有匹配本次参试学生')
    expect(issues).toContain('成绩科目尚未导入或已移除')
    expect(issues).toContain('所选科目不属于本次考试')
  })
})
