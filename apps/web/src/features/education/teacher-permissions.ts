export type TeacherScope = { role: string; grade: string; class_number: string; subject: string }
export type TeacherPermission = {
  teacher_id: string
  score_types: string[]
  score_subjects: string[]
  diagnosis_types: string[]
  diagnosis_subjects: string[]
  essay_types: string[]
  range_type: 'all' | 'grade' | 'class'
  grades: string[]
  classes: string[]
}
export type PermissionTeacher = {
  id: string; platform_id: string; name: string; account: string
  fields: Record<string, string>; duties: string[]; role_labels: string[]
  filter_scopes: TeacherScope[]; scope_classes: string[]; scope_grades: string[]
  default_warnings: string[]; recommendation: TeacherPermission
}
export type TeacherFilters = { search: string; grade: string; classroom: string; subject: string; duty: string }
export const EMPTY_TEACHER_FILTERS: TeacherFilters = { search: '', grade: '', classroom: '', subject: '', duty: '' }
const GRADE_NAMES = ['小学一年级', '小学二年级', '小学三年级', '小学四年级', '小学五年级', '小学六年级', '初中一年级', '初中二年级', '初中三年级', '高中一年级', '高中二年级', '高中三年级']
const text = (value: string) => value.normalize('NFKC').trim()
export const teacherGrade = (value: string) => {
  const grade = text(value)
  return /^\d+$/.test(grade) ? GRADE_NAMES[Number(grade) - 1] || grade : grade
}
const classNumber = (value: string) => {
  const number = text(value).replace(/班$/, '').trim()
  return /^\d+$/.test(number) ? String(Number(number)) : number
}
export const teacherClass = (grade: string, number: string) => `${teacherGrade(grade)} / ${classNumber(number)}`
export const sortTeacherOptions = (values: string[]) => [...new Set(values.filter(Boolean))].sort((a, b) => {
  const gradeA = GRADE_NAMES.indexOf(a.split(' / ')[0]), gradeB = GRADE_NAMES.indexOf(b.split(' / ')[0])
  return (gradeA >= 0 && gradeB >= 0 ? gradeA - gradeB : 0) || a.localeCompare(b, 'zh-CN', { numeric: true })
})

// Every selected dimension, including the duty, must describe the same responsibility.
export function matchesTeacher(teacher: PermissionTeacher, filters: TeacherFilters): boolean {
  if (!`${teacher.name} ${teacher.platform_id} ${teacher.account}`.toLowerCase().includes(text(filters.search).toLowerCase())) return false
  if (filters.duty && !teacher.duties.includes(filters.duty)) return false
  if (!(filters.grade || filters.classroom || filters.subject)) return true
  return teacher.filter_scopes.some(scope =>
    (!filters.duty || scope.role === filters.duty)
    && (!filters.grade || teacherGrade(scope.grade) === teacherGrade(filters.grade))
    && (!filters.classroom || teacherClass(scope.grade, scope.class_number) === filters.classroom)
    && (!filters.subject || text(scope.subject) === text(filters.subject)))
}

export function teacherFilterOptions(teachers: PermissionTeacher[], filters: TeacherFilters) {
  const scopes = teachers.flatMap(teacher => teacher.filter_scopes)
  return {
    grades: sortTeacherOptions(scopes.map(scope => teacherGrade(scope.grade))),
    classes: sortTeacherOptions(scopes.filter(scope => scope.class_number && (!filters.grade || teacherGrade(scope.grade) === teacherGrade(filters.grade)))
      .map(scope => teacherClass(scope.grade, scope.class_number))),
    subjects: sortTeacherOptions(scopes.map(scope => text(scope.subject))),
  }
}

export function permissionDraft(teacher: PermissionTeacher, saved?: TeacherPermission): TeacherPermission {
  const source = saved || teacher.recommendation
  return { teacher_id: teacher.id, score_types: [...source.score_types], score_subjects: [...source.score_subjects],
    diagnosis_types: [...source.diagnosis_types], diagnosis_subjects: [...source.diagnosis_subjects], essay_types: [...source.essay_types],
    range_type: source.range_type, grades: [...source.grades], classes: [...source.classes] }
}

export type PermissionPerson = { id: string; grade: string; class_number: string }
export function permissionPeople(people: PermissionPerson[], form: TeacherPermission): PermissionPerson[] {
  return people.filter(person => form.range_type === 'all'
    || (form.range_type === 'grade' && form.grades.includes(person.grade))
    || (form.range_type === 'class' && form.classes.includes(`${person.grade} / ${person.class_number}`)))
}

export function permissionIssues(form: TeacherPermission, people: PermissionPerson[], subjects: Array<{ subject_id?: string; name: string; student_ids: string[] }>, ready: string[]): string[] {
  const missing = []
  if (!(form.score_types.length || form.diagnosis_types.length || form.essay_types.length)) missing.push('未选择查询内容')
  if (!!form.score_types.length !== !!form.score_subjects.length) missing.push('成绩类型与成绩科目需要同时选择')
  if (!!form.diagnosis_types.length !== !!form.diagnosis_subjects.length) missing.push('诊断类型与诊断科目需要同时选择')
  if ((form.range_type === 'grade' && !form.grades.length) || (form.range_type === 'class' && !form.classes.length)) missing.push('未选择授权年级或班级')
  const selected = new Set(permissionPeople(people, form).map(person => person.id))
  if (!selected.size && !missing.includes('未选择授权年级或班级')) missing.push('学生范围没有匹配本次参试学生')
  if (form.score_subjects.some(id => !ready.includes(id))) missing.push('成绩科目尚未导入或已移除')
  const essayNames: string[] = form.essay_types.map(type => type === 'chinese' ? '语文' : '英语')
  const requested = [...new Set([...form.score_subjects, ...form.diagnosis_subjects])]
  if (requested.some(id => !subjects.some(subject => subject.subject_id === id)) || essayNames.some(name => !subjects.some(subject => subject.name === name))) missing.push('所选科目不属于本次考试')
  const emptySubjects = subjects.filter(subject => (requested.includes(subject.subject_id || '') || essayNames.includes(subject.name)) && !subject.student_ids.some(id => selected.has(id)))
  if (emptySubjects.length) missing.push(`${emptySubjects.map(subject => subject.name).join('、')}在当前学生范围内没有参试学生`)
  return missing
}
