s=section("class-analysis","04","班级分析","按班级 × 学科 × 考试读取聚合；向学生学情下钻。",route="/admin/analysis · /teacher/analysis")
chain(s,"analysis-read","01 · 选择范围与班级统计","分析结果按请求计算，没有独立结果表，也不反写成绩。",[
 {"title":"选择班级 / 学科 / 考试","text":"三项完整才请求分析接口","kind":"actor","api":["GET /api/v1/platform/education/class-analysis?class_id=&subject_id=&exam_id="]},
 {"title":"核验同校与教师任教","text":"有效班级×学科授权；管理员本校","kind":"decision","tables":["teaching_assignments","import_classes","subjects","exams"]},
 {"title":"确定当前班级学生集合","text":"class_id；为空时 external_class_id","kind":"data","tables":["students"],"detail":"按当前班级关系查询，不是考试时名单；实现没有额外过滤 Student.status。停用学生仍可能保留在班级统计样本中。"},
 {"title":"读取该考试学科成绩","text":"StudentSubjectScore + Student","kind":"data","tables":["student_subject_scores"],"detail":"样本量是有该次该科成绩的记录数，不是班级总人数；缺考与未导入没有自动补零。"},
 {"title":"代码计算基础指标","text":"n / average / minimum / maximum","detail":"平均分=sum(score)/n；四个得分率区间：<60%、60%至<80%、≥80%、满分未知。无样本时均分、最大最小值为空。"},
 {"title":"返回分布 + 匿名明细","text":"学生序号 / 分数 / student_id 链接","kind":"outcome","detail":"student_id 用于受权学情下钻；读取写入 education.class.analysis 审计。明细接口再次鉴权。"},
],refs=[src("school","class_analysis"),src("school_ui","ClassAnalysisPage")])
graph(s,"analysis-compare","02 · 上次考试对比与知识点丢分","两条计算支路共享本校、当前班级、学科范围。",[
 n("a1","当前考试与范围","exam_id / class_id / subject_id",1,0,"actor"),
 n("a2","查更早的一次考试","start_date < 当前日期；按日期倒序",0,1,"process",tables=["exams","student_subject_scores"]),
 n("a3","查询小题得分","QuestionScore + 当前班级学生",2,1,"data",tables=["question_scores","students"]),
 n("a4","两次满分有效且一致？","全部 full_score > 0；唯一值为一个",0,2,"decision",detail="两次样本可不同；若当前考试无日期则不生成上次对比。没有同满分条件时 average_delta=null。"),
 n("a5","解析知识点名称","直接 knowledge_point_id 优先",2,2,"process",detail="若无直接知识点名称且存在 question_version_id，查 education_question_tags → education_taxonomy(kind=knowledge)。都未映射则 unknown+1。",tables=["education_question_tags","education_taxonomy"]),
 n("a6","返回可比差值 / 空值","本次均分 - 上次均分；样本量并列",0,3,"outcome"),
 n("a7","返回各知识点丢分","Σlost_score / 题记录数 / 去重学生数",2,3,"outcome",detail="同一小题有多个知识点时，每个标签完整计入丢分；各标签累计不能相加当作总丢分。不据此自动推断掌握状态。"),
 n("a8","学情下钻与教学核验","查看特定学生授权学科和小题",1,4,"outcome",target="student-learning"),
],[e("a1","a2","对比支路"),e("a1","a3","知识点支路"),e("a2","a4"),e("a3","a5"),e("a4","a6","判断可比性"),e("a5","a7","分组聚合"),e("a6","a8"),e("a7","a8")],refs=[src("school","class_analysis")])
note(s,"本模块没有分析结果的增删改","筛选条件只改变读数范围；需要修正时回到学生档案、任教关系、成绩导入或题目标签的生产入口。当前问答工具不调用 class-analysis，也不把同班他人明细发给学生模型。")

s=section("student-learning","05","学生学情","管理侧学生目录与明细；从同源成绩核验问答依据。",route="/admin/students · /teacher/students")
graph(s,"student-roster","01 · 学情目录与角色分流","管理列表先按权限查询，再由浏览器搜索姓名、学号或学校、筛选待跟进。",[
 n("l1","读取学生学情目录","GET /platform/management/students",1,0,"actor"),
 n("l2","学校管理员 / QA","本校 active 学生 + 学校名称",0,1,"process",tables=["students","schools"]),
 n("l3","教师","有效任教班级内 active 学生",2,1,"process",tables=["teaching_assignments","students"]),
 n("l4","按日期选最近总分","ROW_NUMBER 按学生分区取第一条",0,2,"data",detail="考试 start_date 降序、created_at 与 id 降序确定最近记录；与部分问答工具按成绩创建时间的取法不同。",tables=["student_exam_scores","exams"]),
 n("l5","逐学科取最近成绩","仅所授学科；不展示全科总分",2,2,"data",tables=["student_subject_scores","subjects","exams"]),
 n("l6","聚合未结风险数","risk_events: open / acknowledged",1,3,"data",tables=["risk_events"]),
 n("l7","前端搜索 / 待跟进筛选","姓名 + 学号 + 学校；open_risks>0",1,4,"outcome",detail="不从成绩或对话自动生成风险；风险数来自已有 risk_events。此目录无新增、编辑、删除学生按钮，档案生产位于教务模块。"),
],[e("l1","l2","学校范围"),e("l1","l3","任教范围"),e("l2","l4"),e("l3","l5"),e("l4","l6"),e("l5","l6"),e("l6","l7")],refs=[src("platform","management_students"),src("management_ui","StudentRosterPage")])
chain(s,"student-detail","02 · 明细下钻与访问审计","student_id 由路由传入，但权限由服务端重新判定。",[
 {"title":"打开学生详情","text":"/admin/students/:studentId","kind":"actor","api":["GET /api/v1/platform/management/students/{student_id}"]},
 {"title":"重新确认学生可访问","text":"active + school / teaching scope","kind":"decision","detail":"范围不匹配或学生停用返回 404 STUDENT_NOT_FOUND。市级与超级管理员的后端范围存在更宽分支，见权限章节。"},
 {"title":"读取学科历史与小题丢分","text":"最多 200 条学科 / 100 条有丢分小题","kind":"data","tables":["student_subject_scores","question_scores","subjects","exams"]},
 {"title":"判断是否教师单一角色","text":"教师不返回总分；其他管理角色可读","kind":"decision"},
 {"title":"按需读取总分历史","text":"最多 20 次；考试名称与总分","kind":"data","tables":["student_exam_scores"]},
 {"title":"返回学情并记审计","text":"student.learning.read；scope 标记","kind":"outcome","tables":["audit_logs"],"detail":"返回 student、scope、subject_scores、exam_scores、question_losses。这里没有正式报告全文或学生聊天记录返回字段。"},
],refs=[src("details","student_detail"),src("scope","scoped_scores")])
table(s,"管理学情与学生问答对照",["学情字段","事实来源","问答用途","边界"],[
["最近考试 / 总分","student_exam_scores + exams","get_exam_summary / ContextBuilder","不自动产生诊断结论"],
["学科得分 / 满分 / 排名","student_subject_scores + subjects","get_subject_scores / get_rank_change / get_score_trend","教师无未任教学科与总分权限"],
["题号 / 丢分","question_scores","get_question_losses","原题正文还需正式 question_version_id"],
["风险数量","risk_events","未传入六个问答工具","不代表模型已判断风险或成绩自动触发风险"],
])

s=section("reports","06","正式报告原件","从原件上传到正式版本，再到学生授权读取和问答引用。",route="/admin/reports")
chain(s,"report-asset","01 · 原件校验与私有保存","文件原件与结构化摘要独立保存，不自动互相生成。",[
 {"title":"上传正式原件","text":"filename + content_base64","kind":"actor","api":["POST /api/v1/platform/education/assets"]},
 {"title":"文件格式和大小校验","text":"PDF / PNG / JPEG；≤15 MB / ≤100 页","kind":"decision","detail":"扩展名须与签名、解码结果一致；文件名不得含路径/控制字符；图像像素≤3000万；PDF 页尺寸有上限。无解析组件返回 FILE_PARSER_UNAVAILABLE。"},
 {"title":"计算 SHA-256 与页信息","text":"media_type / byte_size / pages"},
 {"title":"保存私有二进制附件","text":"education_assets.content + storage_key","kind":"data","tables":["education_assets"],"detail":"当前落在数据库 LargeBinary；storage_key 是稳定迁移键。没有公开静态 URL。"},
 {"title":"返回附件 asset_id","text":"文件名 / MIME / 大小 / 哈希 / 页数","kind":"outcome"},
 {"title":"开始绑定新报告版本","text":"学生 / 考试 / 学科 / 类型 / 版本","kind":"actor"},
],refs=[src("curriculum","inspect_file"),src("curriculum","upload_asset"),src("report_ui","ReportWorkbenchPage")])
graph(s,"report-version","02 · 新报告版本与重复冲突","原件不能复用给另一报告；纠错采用新增版本。",[
 n("v1","填写正式报告元数据","学生 / 考试 / 类型 / 版本 / 时间",0,0,"actor"),
 n("v2","填写正式摘要与原文","summary 必填；raw_content 可空",1,0,"actor",detail="学科可空。类型有 diagnosis、score_report、marked_work。structured_json 由此入口保存 {summary}；不自动 OCR 或批改报告。"),
 n("v3","核验全部对象归属","学生 / 考试 / 学科 / 原件必须同校",2,0,"decision"),
 n("v4","核验版本与附件用途","学生+考试+学科+类型+版本不重复",2,1,"decision",detail="重复版本 REPORT_VERSION_EXISTS；附件已属于报告或试卷 ASSET_PURPOSE_CONFLICT。变更正文需新增版本和独立原件。"),
 n("v5","新增正式报告记录","status=generated；source_system=native",1,1,"data",tables=["diagnosis_reports"],api=["POST /api/v1/platform/education/reports"]),
 n("v6","固定报告-原件关联","report_id → asset_id；保存审计",0,1,"data",tables=["education_report_attachments","audit_logs"]),
 n("v7","学校端列表回读","学生 / 考试 / 版本 / 来源 / 原件",0,2,"outcome"),
 n("v8","学生端仍需独立授权","未自动写 student_entitlements",1,2,"decision",tables=["student_entitlements"],detail="上传成功不自动授予学生 DIAGNOSIS 权益；当前五模块没有权益开通/撤销管理接口。"),
 n("v9","满足权益后可读取","报告页 / 原文 / 原件 / get_diagnosis",2,2,"outcome",target="routing"),
],[e("v1","v2"),e("v2","v3"),e("v3","v4"),e("v4","v5","通过"),e("v5","v6"),e("v6","v7"),e("v7","v8","学生尝试打开"),e("v8","v9","命中具体范围")],refs=[src("learning","create_report"),src("curriculum","assert_asset_purpose"),src("grants","authorized_reports")])
graph(s,"report-access","03 · 学生读报告、原件与问答引用","所有读取路径都需要匹配当前有效权益。",[
 n("p1","学生请求报告内容","列表 / 原文 / 版本 / 原件 / Tool",1,0,"actor"),
 n("p2","有效 DIAGNOSIS 授权？","active；starts_at≤now；未过期",1,1,"decision",tables=["student_entitlements"],detail="product_code 为 DIAGNOSIS 或 DIAGNOSIS_REPORT；资源类型和 resource_id 组合必须合法。"),
 n("p3","没有权益：403","ENTITLEMENT_REQUIRED + 拒绝审计",0,1,"error"),
 n("p4","本人、正式与资源匹配？","school + student + status=generated",1,2,"decision",detail="授权范围：全学生、指定 exam、指定 report/diagnosis_report 或指定 subject。不匹配 REPORT_NOT_AVAILABLE；不能只根据前端权益标签放行。"),
 n("p5","原文 / 文件存在？","raw_content / asset_id 分别检查",0,3,"decision",detail="原文为空 REPORT_SOURCE_MISSING。附件缺失显示尚未接入；摘要不当作原件。附件接口再次调用 require_report。"),
 n("p6","问答只取结构化报告","report_id / version / structured / 时间",2,3,"outcome",detail="get_diagnosis 返回 structured_json，不自动把 PDF 字节或 raw_content 注入模型；subject_name 尚未实际参与工具筛选。",target="routing"),
 n("p7","受权原件 Blob / 原文","no-store / nosniff；读取审计",0,4,"outcome",tables=["education_assets","audit_logs"]),
 n("p8","固化引用、打开再鉴权","sources 保留版本、摘要与来源",2,4,"data",tables=["chat_messages"]),
],[e("p1","p2"),e("p2","p3","无有效授权","error"),e("p2","p4","有授权"),e("p4","p5","页面读取"),e("p4","p6","Tool 调用"),e("p5","p7","对应内容存在"),e("p6","p8")],refs=[src("grants","require_report"),src("education","asset_access"),src("platform","student_diagnosis_source"),src("analysis_tool","GetDiagnosisTool")])
note(s,"版本生命周期","报告管理当前提供列表和新增版本；没有编辑既有正文、删除报告、下架报告、覆盖附件或授予权益的接口。模型中的 status 字段并不等于存在对应管理操作。", "warn")
