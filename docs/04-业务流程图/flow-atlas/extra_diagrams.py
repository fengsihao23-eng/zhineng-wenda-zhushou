# Explicit lifecycle and entity relations supplement the module flows.
s=next(x for x in DATA["sections"] if x["id"]=="imports")
graph(s,"import-states","04 · 导入状态机与合法重试","状态保存在 education_imports.status；修订号与冻结规则共同决定能否执行。",[
 n("st1","uploaded","文件已保存；未完成预检",0,0,"data"),
 n("st2","预检 + revision校验","校验映射、身份引用与数值",1,0,"decision"),
 n("st3","invalid","有逐行错误；修映射或重传新批次",2,0,"error"),
 n("st4","ready","所有检查通过；report.ok=true",1,1,"outcome"),
 n("st5","running","确认接受；后台复核和事务写入",1,2,"process"),
 n("st6","succeeded","事务提交；progress=100；内容冻结",2,2,"outcome"),
 n("st7","failed","事务失败或二次预检失败",0,2,"error"),
 n("st8","核对失败后的report.ok","false先预检；true可同修订确认重试",0,3,"decision"),
],[e("st1","st2"),e("st2","st3","预检失败","error"),e("st3","st2","修正映射再预检"),e("st2","st4","通过"),e("st4","st5","confirm"),e("st5","st6","commit"),e("st5","st7","失败","error"),e("st7","st8","修复后"),e("st8","st5","可重试"),e("st8","st2","需重新预检",via="left")],refs=[src("imports","preflight"),src("imports","confirm"),src("imports","execute_import")],note="running / succeeded 的重复确认返回原工作区，不重复导入；这两个状态不能再改变 mapping。")
s=next(x for x in DATA["sections"] if x["id"]=="lineage")
graph(s,"entity-keys","02 · 核心实体关系与实际连接键","箭头标明引用关系或逻辑关联；物理外键及复合约束以数据字典为准。",[
 n("k1","users → students","users.id = students.user_id",0,0,"data",tables=["users","students"],detail="学生账号一对一绑定约束独立于导入档案。学校和学生状态在本人入口重新校验。"),
 n("k2","import_classes","班级ID / external_class_id",1,0,"data",tables=["import_classes"]),
 n("k3","teaching_assignments","teacher_user_id / class_id / subject_id",2,0,"data",tables=["teaching_assignments"]),
 n("k4","student_exam_scores","唯一：student_id + exam_id",0,1,"data",tables=["student_exam_scores"]),
 n("k5","exams + subjects","exam_subjects关联考试与学科",1,1,"data",tables=["exams","subjects","exam_subjects"]),
 n("k6","student_subject_scores","唯一：学生 + 考试 + 学科",2,1,"data",tables=["student_subject_scores"]),
 n("k7","question_scores","唯一：学生 + 考试 + 学科 + 题号",0,2,"data",tables=["question_scores"]),
 n("k8","education_question_versions","正文版本 → 正式题目 / 试卷版本",1,2,"data",tables=["education_question_versions","education_questions","education_paper_versions"]),
 n("k9","diagnosis_reports","学生 + 可选考试/学科 + 类型 + 版本",2,2,"data",tables=["diagnosis_reports","student_entitlements"]),
 n("k10","chat_messages.sources","resource_id指成绩行 / 报告ID",0,3,"data",tables=["chat_messages"]),
 n("k11","education_sources","native_id指业务记录；source_version固定",1,3,"data",tables=["education_sources"]),
 n("k12","report_attachments → assets","report_id → asset_id → content",2,3,"data",tables=["education_report_attachments","education_assets"]),
],[e("k1","k2","当前班级关联"),e("k2","k3","班级授权"),e("k1","k4","student_id"),e("k5","k4","exam_id"),e("k5","k6","exam_id+subject_id"),e("k3","k6","读取范围"),e("k4","k7","同学生/考试逻辑关联"),e("k7","k8","question_version_id"),e("k6","k9","同学生/考试逻辑关联"),e("k7","k10","resource_id"),e("k8","k11","source_id"),e("k9","k12","report_id")],refs=[src("apps/api/app/db/models/score.py"),src("apps/api/app/db/models/education.py"),src("apps/api/app/db/models/chat.py")])
# Replace visually sequential exception nodes with actual branching edges.
chat=next(x for x in DATA["sections"] if x["id"]=="chat")
d=next(d for d in chat["diagrams"] if d["id"]=="chat-stream")
d["edges"]=[e(f"chat-stream-{i}",f"chat-stream-{i+1}") for i in range(1,6)]+[
 e("chat-stream-2","chat-stream-7","异常 / 取消","error",via="left"),
 e("chat-stream-7","chat-stream-8","同ID重试"),
 e("chat-stream-6","chat-stream-9","用户选择归档")]
d["note"]="红色分支为执行异常或取消；归档是用户单独操作。成功回答不会自动执行异常清理或归档。"
d=next(d for d in chat["diagrams"] if d["id"]=="chat-evidence")
d["edges"]=[e(f"chat-evidence-{i}",f"chat-evidence-{i+1}") for i in range(1,7)]+[
 e("chat-evidence-7","chat-evidence-8","权限通过"),e("chat-evidence-7","chat-evidence-9","权限拒绝","error",via="bottom")]
d["note"]="普通历史消息回读与依据下钻接口的报告权益策略存在差异，详见实现差异清单。"
DATA["tableInfo"]["token_revocations"]=DATA["tableInfo"].pop("revoked_tokens")
routing=next(x for x in DATA["sections"] if x["id"]=="routing")
d=routing["diagrams"][0]
for node in d["nodes"]:
    if node["id"]=="t4":node["col"]=2
    if node["id"]=="t6":node["col"]=0
    if node["id"] in {"t1","t2","t3","t4","t5","t6"}:node["kind"]="decision"
d["edges"]=[e("t0","t1","开始规则匹配")]+[e(f"t{i}",f"t{i+1}","未命中继续") for i in range(1,7)]
d["note"]="任一节点命中即执行该节点列出的工具，随后进入模型与审核；不再检查后续规则。选定学科时，考试概览工具会改为学科成绩工具。"
