import { describe, expect, it } from 'vitest'
import { targetsFor, filenameFor, parseReportFilename, fuzzyMatches, type ExamScope, type Classification } from './report-management'

const scope: ExamScope = { id: 'exam', exam_code: 'EX-20261019-001', name: '合成考试', school: '合成学校', academic_year: '2026-2027', exam_date: '2026-10-19', revision: 1,
  subject_names: ['语文', '英语'], grades: ['高一'], classes: ['高一|1班', '高一|2班'],
  subjects: [{ subject_id: 'cn', name: '语文', student_ids: ['a', 'b'] }, { subject_id: 'en', name: '英语', student_ids: ['a'] }],
  snapshots: { a: { id: 'a', name: '同名', platform_id: '10000001', account: 'account-a', grade: '高一', class_number: '1班' }, b: { id: 'b', name: '同名', platform_id: '10000002', account: 'account-b', grade: '高一', class_number: '2班' } }, teachers: [] }
const row: Classification = { category: 'diagnostic', report_type: 'student', subject_ids: ['cn'] }

describe('r86 filename recognition uses saved exam identities', () => {
  it('distinguishes students with the same name using their platform ID', () => {
    for (const target of ['a', 'b']) expect(parseReportFilename(filenameFor(scope, row, target), scope, row)).toEqual({ target, errors: [] })
  })
  it('accepts the unique saved account as an alternative to the platform ID', () => {
    const name = filenameFor(scope, row, 'a').replace('10000001', 'account-a')
    expect(parseReportFilename(name, scope, row).target).toBe('a')
  })
  it('rejects wrong exams, names, subjects and types', () => {
    const name = filenameFor(scope, row, 'a')
    for (const invalid of [name.replace(scope.exam_code, 'OTHER'), name.replace('同名', '错名'), name.replace('语文', '英语'), name.replace('个人学情诊断', '个人作文批改报告'), '随便命名.pdf']) {
      expect(parseReportFilename(invalid, scope, row).errors.length).toBeGreaterThan(0)
    }
  })
  it('rejects multiple subjects in one upload batch', () => {
    expect(parseReportFilename('anything.pdf', scope, { ...row, subject_ids: ['cn', 'en'] }).errors).toContain('每批只能上传一个科目')
  })
  it('limits candidate people to selected subject participation', () => {
    expect(targetsFor(scope, { ...row, subject_ids: ['en'] }).map(item => item.value)).toEqual(['a'])
    expect(targetsFor(scope, { ...row, subject_ids: ['cn', 'en'] }).map(item => item.value)).toEqual(['a'])
  })
  it('recognizes classes, grades and the school target with their own patterns', () => {
    for (const [type, target] of [['classAll', '高一|1班'], ['gradeSubject', '高一'], ['school', 'school']]) {
      const config = { ...row, report_type: type }
      expect(parseReportFilename(filenameFor(scope, config, target), scope, config)).toEqual({ target, errors: [] })
    }
  })
  it('keeps Chinese and English essay identities distinct', () => {
    const essay = { category: 'essay', report_type: 'essay', subject_ids: ['en'] } as Classification
    expect(parseReportFilename(filenameFor(scope, essay, 'a'), scope, essay).target).toBe('a')
    expect(parseReportFilename(filenameFor(scope, essay, 'a'), scope, { ...essay, subject_ids: ['cn'] }).errors.length).toBeGreaterThan(0)
  })
  it('fuzzy searches names, IDs and accounts with multiple normalized terms', () => {
    const candidates = targetsFor(scope, row)
    expect(fuzzyMatches(candidates, '同名 ACCOUNT-A').map(item => item.value)).toEqual(['a'])
    expect(fuzzyMatches(candidates, '１００００００２').map(item => item.value)).toEqual(['b'])
  })
})
