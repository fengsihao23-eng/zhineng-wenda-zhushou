'use strict';
const TYPES = {student:'个人学情诊断',classAll:'班级综合诊断',classSubject:'班级单科诊断',
  gradeAll:'年级综合诊断',gradeSubject:'年级单科诊断',school:'全校学情诊断',essay:'个人作文批改报告'};
function reports(rows, exams) {
  const subjects = [].concat.apply([], exams.map(e => e.subjects));
  return rows.map(row => Object.assign({}, row, {
    label: row.category==='essay' ? TYPES.essay : TYPES[row.type] || '学情报告',
    examName: (exams.find(e=>e.id===row.examId)||{}).name || '相关考试',
    subjectLabel: row.subjects.map(id=>(subjects.find(s=>s.k===id)||{}).n || id).join('、')
  }));
}
function messages(rows, exams, reports) {
  const subjects = [].concat.apply([], exams.map(e=>e.subjects));
  return rows.map(row=>Object.assign({}, row, {
    time: (row.at || '').slice(11,16),
    table: (row.table || []).map(item=>Object.assign({}, item, {percent:Math.max(0,Math.min(100,item.max ? item.score/item.max*100 : 0))})),
    sources: (row.sources || []).map(ref=>Object.assign({}, ref, {
      label: ref.kind==='report' ? (reports.find(r=>r.id===ref.reportId)||{}).label || '报告来源' : ((subjects.find(s=>s.k===ref.subject)||{}).n || '科目')+'成绩 · 考务管理',
      examName: (exams.find(e=>e.id===ref.examId)||{}).name || '相关考试'
    }))
  }));
}
module.exports = {reports, messages};
