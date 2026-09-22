# Business diagrams. Executed by build_atlas.py with declarative helpers.
s=section("overview","00","一张图看清整条链路","从教务档案、成绩与报告原件，到学生提问、事实查询、回答与依据回读。",group="全局视图",intro="以截图中的五个学校端模块为主线，展开当前工作区实际代码。每个节点都可点击查看处理规则、数据表、接口和源码定位。")
graph(s,"ecosystem","业务生产 → 数据事实 → 教学分析 / 智能问答","箭头表示明确的数据供给或处理顺序；页面之间共享底层事实，不意味着问答直接调用管理页面。",[
 n("o1","师生班级与考试","师生身份 · 班级 · 任教 · 考试科目",0,0,"module",tables=["users","students","import_classes","teaching_assignments","exams","subjects"],target="school"),
 n("o2","成绩导入","8 类 CSV → 映射 → 预检 → 确认",1,0,"module",tables=["education_imports","data_import_batches"],target="imports"),
 n("o3","正式报告原件","PDF / PNG / JPEG + 正式摘要",2,0,"module",tables=["diagnosis_reports","education_assets"],target="reports"),
 n("o4","身份、归属与授权","school_id / student_id / 任教范围",0,1,"data",detail="学生账号通过 students.user_id 绑定；教师访问按当前有效班级×学科任教关系过滤；学生诊断报告另查 student_entitlements。",tables=["students","teaching_assignments","student_entitlements"],target="permissions"),
 n("o5","三类成绩事实","总分 · 学科成绩 · 小题得分",1,1,"data",tables=["student_exam_scores","student_subject_scores","question_scores"],target="data"),
 n("o6","报告正文、附件与版本","structured_json / raw_content / asset_id",2,1,"data",tables=["diagnosis_reports","education_report_attachments","education_assets"],target="reports"),
 n("o7","班级分析","样本 / 均分 / 分布 / 知识点丢分",0,2,"module",detail="读取成绩事实并按当前班级归属汇总；没有独立的班级分析结果业务表，不写回学生成绩。",target="class-analysis"),
 n("o8","学生学情","最近成绩 / 任教学科 / 小题 / 风险",1,2,"module",target="student-learning"),
 n("o9","本人上下文 + 六个工具","成绩概览 / 学科 / 对比 / 趋势 / 丢分 / 报告",2,2,"process",detail="当前主链路每轮最多一个确定性工具；规则未命中时走 general_chat。报告工具返回结构化报告，不自动读取 PDF。",target="routing"),
 n("o10","问答请求","账号校验 → 本人会话 → 考试 / 学科范围",0,3,"module",tables=["chat_sessions","chat_messages"],target="chat"),
 n("o11","模型表达 + 响应检查","Prompt + 本人事实 → 模型 → Guard",1,3,"process",target="chat"),
 n("o12","答案、引用与回访","sources 固化 → 依据回读 → 反馈 / 人工支持",2,3,"outcome",tables=["chat_messages","platform_feedback","human_handoffs"],target="support"),
],[e("o1","o2","提供身份映射"),e("o1","o4","建立边界"),e("o2","o5","事务提交"),e("o3","o6","固定版本"),e("o4","o7","教师 / 学校范围"),e("o5","o8","同源读取"),e("o6","o9","报告级授权后"),e("o5","o7","聚合读取"),e("o5","o9","本人事实查询"),e("o7","o8","下钻学生详情"),e("o10","o11","发起处理"),e("o9","o11","结构化事实"),e("o11","o12","审核后整段输出")],refs=[src("nav_ui"),src("agent","run"),src("school","class_analysis")])
note(s,"阅读范围","梳理基线：2026-09-18 当前工作区源码，包含尚未提交的实现。数据名称来自模型、接口及 CSV 契约；没有读取实际学生数据，也没有验证生产部署。")
note(s,"先分清三类数据","事实：分数、排名、小题丢分；正式材料：报告摘要、原文、不可变附件；衍生结果：班级汇总、趋势差值、模型解释。三个层次在图中分别标示。")
table(s,"五个模块分别为问答提供什么",["模块 / 页面","生产或读取的数据","对应智能问答能力","接入方式"],[
["师生班级与考试 /admin/school","学生账号绑定、学校、班级、学科、考试、教师任教","谁能问、问谁的数据、可选考试与学科","身份与数据范围；不向模型开放管理写操作"],
["成绩导入 /admin/imports","student_exam_scores / student_subject_scores / question_scores","总分、各科、排名对比、趋势、小题丢分","六工具中的前五个 + 动态上下文"],
["班级分析 /admin/analysis","按班级、学科、考试即时汇总","当前没有班级汇总问答工具","与问答共用成绩表；结果未传入学生 Agent"],
["学生学情 /admin/students","当前学生目录、总分或任教学科、小题丢分、风险数","本人数据问答的数据核验入口","管理查询与学生 Tool 分别做权限过滤"],
["正式报告原件 /admin/reports","diagnosis_reports + education_report_attachments + education_assets","正式诊断 / 学习建议的已授权依据","get_diagnosis 返回 structured_json；原件由受权接口打开"],
])

s=section("relations","01","模块之间如何衔接","把页面跳转、数据写入、共享读取与未接通的链路分别说明。",group="全局视图")
graph(s,"relations-data","模块级数据依赖图","教师任教限制管理侧读数；报告权益限制学生侧读数；双方不是同一种授权。",[
 n("r1","学校 / 班级 / 学生","schools → import_classes → students",0,0,"data",tables=["schools","import_classes","students"]),
 n("r2","考试 / 学科 / 满分","exams + subjects → exam_subjects",1,0,"data",tables=["exams","subjects","exam_subjects"]),
 n("r3","成绩导入事务","CSV 外部 ID → 本校内部 UUID",2,0,"process",target="imports"),
 n("r4","班级分析读模型","聚合均分 / 分布 / 知识点丢分",0,1,"process",target="class-analysis"),
 n("r5","成绩事实主表","总分 / 学科 / 小题，按业务键更新",1,1,"data",tables=["student_exam_scores","student_subject_scores","question_scores"]),
 n("r6","学生学情读模型","学生目录 → 授权明细 → 访问审计",2,1,"process",target="student-learning"),
 n("r7","试卷 / 正式题目 / 标签","题目版本和知识点关联补全",0,2,"data",tables=["education_question_versions","education_question_tags","education_taxonomy"],target="support"),
 n("r8","本人问答查询工具","只读结构化事实与正式报告",1,2,"process",target="routing"),
 n("r9","报告 + 当前有效权益","report_id / exam_id / subject_id 匹配",2,2,"data",tables=["diagnosis_reports","student_entitlements"]),
 n("r10","知识文档治理","knowledge_documents 的审核与发布",0,3,"gap",detail="有文档治理接口，但没有进入当前 Agent 的检索/RAG 调用。不能把“已发布文档”画成“问答已使用”。",tables=["knowledge_documents"],target="gaps"),
 n("r11","回答证据快照","chat_messages.sources / selected_context",1,3,"data",tables=["chat_messages"]),
 n("r12","问答反馈与支持","反馈队列、工单消息、处理回读",2,3,"outcome",target="support"),
],[e("r1","r2","配置业务范围"),e("r2","r3","引用必须可解析"),e("r3","r5","原子写入"),e("r5","r4","按当前班级聚合"),e("r5","r6","按学生读取"),e("r7","r5","固定小题版本"),e("r5","r8","查询本人分数"),e("r9","r8","动态授权报告"),e("r8","r11","固化生成时依据"),e("r11","r12","关联 message_id")],refs=[src("importer","_upsert_domain"),src("learning","pin_sources"),src("management_ui","KnowledgePage")])
table(s,"跨模块的关键连接键",["连接","字段 / 关联规则","影响"],[
["账号 → 学生","users.id = students.user_id；school_id 相同；学生与账号均 active","导入档案不自动变成可登录账号；绑定冲突拒绝覆盖"],
["班级 → 学生","students.class_id 优先；为空时用本校 external_class_id 匹配 import_classes","转班影响下次班级分析；历史成绩没有考试时班级快照"],
["教师 → 学生 / 成绩","teaching_assignments.teacher_user_id + class_id + subject_id + 有效时间","班级和学科必须是同一条匹配授权，不能并集扩大"],
["考试 → 学科","exam_subjects(exam_id, subject_id)；full_score","教务编辑有历史引用保护；CSV 更新路径的保护存在差异"],
["小题得分 → 原题","question_scores.question_version_id → education_question_versions.id","原题依据一旦固定，不允许静默换版本"],
["正式报告 → 原件","education_report_attachments.report_id → diagnosis_reports.id；asset_id → education_assets.id","报告原件不可复用于试卷或另一报告"],
["历史回答 → 事实来源","sources[].type / resource_id / facts / provenance；selected_context","回答时的事实留在消息里；打开依据重新鉴权"],
])

s=section("school","02","师生班级与考试","六个子页签：班级、学生与账号、教师账号、教师任教、学科、考试科目。",route="/admin/school")
chain(s,"school-entry","01 · 教务读写共用入口","所有写入先认证与锁定本校，再进入对象级校验。",[
 {"title":"打开学校工作台","text":"选择六类对象 / 搜索名称 / 翻页","kind":"actor","api":["GET /api/v1/platform/education/school/{kind}"]},
 {"title":"读取数据库身份与角色","text":"users + user_roles + roles","kind":"decision","tables":["users","user_roles","roles"],"detail":"用户状态必须有效；school_id 和角色从数据库读取，不信任客户端传入的可变身份声明。"},
 {"title":"分配只读 / 写权限","text":"写：SCHOOL_ADMIN / SUPER_ADMIN","kind":"decision","detail":"QA 只读。TEACHER 仅允许任教相关选项，不可维护教师账号；一般 CITY_OPERATOR 没有该教务写权限。"},
 {"title":"本校归属 + 写入校验","text":"owned / native_only / 业务引用检查","kind":"process","detail":"写接口先锁 schools 行；更新已有对象锁定目标行。外部来源记录走来源接收流程，不能使用原生编辑接口。"},
 {"title":"事务写入与操作回执","text":"新增可幂等 · 更新保留历史","kind":"data","tables":["operation_receipts","audit_logs"],"detail":"claim() 以学校、操作者、操作、幂等键或内容哈希保留回执；IntegrityError 统一回滚为 409。更新接口不都使用 revision，不能宣称全部有乐观版本控制。"},
 {"title":"返回服务端最新记录","text":"重新读取列表 / 状态 / 详情","kind":"outcome"},
],refs=[src("education","writer"),src("school","listing"),src("common","claim")])
graph(s,"school-class","02 · 班级新增、修改、停用与引用阻断","班级采用 active / inactive；没有物理删除接口。",[
 n("c1","新增班级","external_class_id + name",0,0,"actor",api=["POST /api/v1/platform/education/school/classes"]),
 n("c2","校验本校唯一标识","school_id + external_class_id",1,0,"decision",tables=["import_classes"]),
 n("c3","写入班级档案","source_system=native；status=active",2,0,"data",tables=["import_classes"]),
 n("c4","选择修改 / 停用","name / status",0,1,"actor",api=["PUT /api/v1/platform/education/school/classes/{id}"]),
 n("c5","原生记录且允许变更？","停用时查在籍学生 + 有效任教",1,1,"decision",detail="检查 students.status=active 的当前班级归属；检查 teaching_assignments.status=active 的引用。外部来源返回 EXTERNAL_READ_ONLY。",tables=["students","teaching_assignments"]),
 n("c6","允许：保存名称或状态","inactive 保留班级与历史成绩",2,1,"outcome",tables=["import_classes","audit_logs"]),
 n("c7","有引用：拒绝停用","409 CLASS_REFERENCED",1,2,"error",detail="先转移或停用在籍学生、调整有效任教关系，再重新提交。不会级联删除成绩、报告或会话。"),
 n("c8","下次按新归属读数","班级统计 / 任教范围随当前关系变化",2,2,"outcome",target="lineage"),
],[e("c1","c2"),e("c2","c3","唯一且有效"),e("c3","c6","后续维护"),e("c4","c5"),e("c5","c6","通过"),e("c5","c7","仍有引用","error"),e("c6","c8")],refs=[src("school","create"),src("school","update_record")])
graph(s,"school-student","03 · 学生档案、转班、停用与账号绑定","档案与登录身份分开；姓名不是跨系统合并键。",[
 n("s1","新增学生档案","外部学生 ID / 学号 / 姓名 / class_id",0,0,"actor",api=["POST /api/v1/platform/education/school/students"]),
 n("s2","核验班级与身份约束","本校有效班级；外部 ID / 学号唯一",1,0,"decision"),
 n("s3","保存 students","source_system=native；账号可未绑定",2,0,"data",tables=["students"]),
 n("s4","修改班级 / 状态","只提交 class_id + active / inactive",0,1,"actor",detail="原生学生更新接口没有姓名或学号字段；外部来源档案不能用该接口修改。停用不删除成绩。",api=["PUT /api/v1/platform/education/school/students/{id}"]),
 n("s5","当前归属更新","class_id 优先于 external_class_id",1,1,"data",tables=["students"],detail="转班改变基于当前班级归属的教师访问和班级分析；学生本人历史得分仍通过稳定 student_id 关联。"),
 n("s6","选定已有学生账号","users.status=active + STUDENT 角色",0,2,"actor",api=["POST /api/v1/platform/education/school/students/{id}/bind"]),
 n("s7","账号和档案是否冲突？","同校；未被其他档案使用；不覆盖旧绑定",1,2,"decision",tables=["users","roles","user_roles","students"]),
 n("s8","写入 students.user_id","下次登录可定位本人数据",2,2,"outcome",target="chat"),
 n("s9","拒绝错误身份关联","409 ACCOUNT_BINDING_CONFLICT",1,3,"error",detail="账号已被另一个学生档案占用，或当前学生已有其他 user_id 时拒绝。当前模块没有解绑/换绑接口。"),
],[e("s1","s2"),e("s2","s3"),e("s4","s5","本校原生记录"),e("s6","s7"),e("s7","s8","没有冲突"),e("s7","s9","已有绑定","error"),e("s3","s8","可另行绑定",via="right")],refs=[src("school","bind_student"),src("schemas","StudentUpdate"),src("auth","get_current_student")])
chain(s,"school-teaching","04 · 教师账号与任教授权","新增教师账号不在本模块；这里维护已有账号及班级×学科授权。",[
 {"title":"读取本校教师账号","text":"users + roles.code=TEACHER","kind":"data","tables":["users","roles","user_roles"]},
 {"title":"编辑显示名或停用账号","text":"display_name / status","api":["PUT /api/v1/platform/education/school/teachers/{id}"],"detail":"停用账号会使后续认证拒绝；任教关系保留，未物理删除。不存在本模块新增教师或重置密码接口。"},
 {"title":"新增 / 编辑任教关系","text":"教师 + 班级 + 学科 + 生效 / 到期","api":["POST /api/v1/platform/education/school/teaching","PUT /api/v1/platform/education/school/teaching/{id}"]},
 {"title":"验证授权主体与时间","text":"教师 active；班级 active；时间含时区","kind":"decision","detail":"expires_at 必须晚于 starts_at。授予 active 任教关系时班级必须有效；教师必须是本校有效 TEACHER 账号。"},
 {"title":"保存 teaching_assignments","text":"唯一：学校 + 教师 + 班级 + 学科","kind":"data","tables":["teaching_assignments"]},
 {"title":"每次读取重新判定","text":"active + starts_at≤now<expires_at","kind":"outcome","detail":"同一学生的班级与学科必须同时命中任教关系。停用/过期后下次查询不再开放，不能读取未任教学科总分。","target":"permissions"},
],refs=[src("school","validate_teaching"),src("school","update_teacher"),src("scope","scoped_scores")])
graph(s,"school-exams","05 · 学科、考试与考试满分","学科当前只支持新增 / 查询；考试支持新增、编辑、停用。",[
 n("x1","创建学科","external_subject_id / code / name",0,0,"actor",api=["POST /api/v1/platform/education/school/subjects"]),
 n("x2","保存 subjects","同校 code 唯一",1,0,"data",tables=["subjects"]),
 n("x3","创建 / 编辑考试","外部 ID / 名称 / 类型 / 日期 / 状态",2,0,"actor",api=["POST /api/v1/platform/education/school/exams","PUT /api/v1/platform/education/school/exams/{id}"]),
 n("x4","保存考试范围","起止日期合法；原生记录可编辑",2,1,"data",tables=["exams"]),
 n("x5","配置学科与满分","subject_id / full_score > 0 且 ≤10000",1,1,"actor",api=["PUT /api/v1/platform/education/exams/{id}/subjects"]),
 n("x6","历史学科成绩已引用？","检查同考试同学科成绩记录",0,1,"decision",tables=["student_subject_scores"]),
 n("x7","改变满分被阻断","409 EXAM_SUBJECT_REFERENCED",0,2,"error"),
 n("x8","新增或保持同满分","写 exam_subjects → 返回考试详情",1,2,"outcome",tables=["exam_subjects"]),
 n("x9","提供数据解释上下文","考试日期 / 学科名称 / 分母口径",2,2,"outcome",target="routing"),
],[e("x1","x2"),e("x2","x3","配置配套考试"),e("x3","x4"),e("x4","x5"),e("x5","x6"),e("x6","x7","已有成绩且改满分","error"),e("x6","x8","无冲突"),e("x8","x9")],refs=[src("school","set_exam_subject"),src("schemas","ExamCreate")],note="该历史保护对应教务编辑接口。CSV 导入可更新 exam_subjects.full_score，当前未见跨批次历史满分一致性检查；详见实现差异。")
table(s,"教务模块操作边界",["对象","新增","修改","删除 / 停用","问答影响"],[
["班级","外部标识 + 名称","原生记录名称 / 状态","只有停用；有效学生或任教引用阻断","教师范围；班级统计"],
["学生","档案与班级","原生记录班级 / 状态；单独账号绑定","只有停用；无解绑接口","本人身份查找；停用后无法获取学生上下文"],
["教师账号","未提供开通接口","显示名称 / active、inactive","停用账号；保留任教关系","教师管理侧访问资格"],
["任教关系","教师×班级×学科×有效期","可改关系字段及状态","设 inactive；无 DELETE","授权到期/停用后次次校验"],
["学科","外部标识 + 代码 + 名称","当前无 PUT","当前无删除 / 停用接口","科目匹配与成绩查询标签"],
["考试与科目","考试 + 科目满分","原生考试元数据 / 状态；受保护的满分","考试 inactive；无考试/科目关系删除接口","选择考试、趋势顺序、分数分母；查询不普遍过滤考试 inactive"],
])

s=section("imports","03","成绩导入","八种明确命名的 CSV；展示上传、映射、预检、写入、失败与重试的完整流程。",route="/admin/imports")
chain(s,"import-read","01 · 上传与列映射","源文件保存在私有工作区；上传本身不写入学生成绩。",[
 {"title":"准备 8 个固定 CSV","text":"UTF-8 / UTF-8 BOM；每批仅本校","kind":"actor","detail":"schools.csv、classes.csv、students.csv、exams.csv、subjects.csv、student_exam_scores.csv、student_subject_scores.csv、question_scores.csv。缺文件在预检报 FILE_MISSING；无数据的文件也可保留表头。"},
 {"title":"文件结构检查","text":"总计 ≤5 MB / 5000 行 / ≤60 列","kind":"decision","detail":"拒绝未知文件名、路径、重复/空表头、列数不匹配、单元格超过 5000 字符。文件内容先以文本 JSON 提交。"},
 {"title":"批次幂等检查","text":"school_id + batch_key + 内容哈希","kind":"decision","detail":"同编号同文件内容且同 source_system 返回原工作区；同编号异内容 409 BATCH_CONTENT_CONFLICT。"},
 {"title":"保存 uploaded 工作区","text":"files / mapping / content_hash / revision=1","kind":"data","tables":["education_imports"],"api":["POST /api/v1/platform/education/imports"]},
 {"title":"映射目标字段 → 源列","text":"同名自动映射；可应用模板修订","detail":"预检接收完整 mapping 与 expected_revision。映射只能使用已知目标字段和文件中实际存在的列。"},
 {"title":"可保存映射模板新版本","text":"同校 name + version 唯一；不覆盖旧模板","kind":"outcome","tables":["education_mapping_templates"],"api":["POST /api/v1/platform/education/mapping-templates"]},
],refs=[src("imports","read_files"),src("imports","upload"),src("education","template_create")])
graph(s,"import-validate","02 · 预检与逐行修正","预检读取映射后的值，先检查整批引用，再检查数值和数据库已有身份。",[
 n("i1","提交最新映射","mapping + expected_revision",0,0,"actor",api=["POST /api/v1/platform/education/imports/{id}/preflight"]),
 n("i2","工作区可修改？","running / succeeded 不允许再映射",1,0,"decision"),
 n("i3","校验字段、整批引用","必填 / 重复行 / 学校、学生、考试、学科",2,0,"process",detail="当前写入器依赖批内学校、学生、考试、学科字典；不是只传一张成绩表即可增量解析任意数据库已有对象。学校代码必须为当前学校，schools.csv 恰好一行。"),
 n("i4","数值与同批口径核对","分数有限且非负；满分、排名、人数有效",2,1,"process",detail="得分≤满分；lost_score=full_score-score；同一考试同一学科满分在该批内一致；排名和人数为正整数；普通数值上限 100000。"),
 n("i5","数据库已有引用核对","学号/外部 ID 冲突；正式题版本固定",1,1,"process",detail="题目版本须属本校同学科、已发布、未删除；已固定得分依据不能换题。字段长度和外部身份映射也在此校验。"),
 n("i6","整批通过？","plan.ok；最多保留 1000 项问题",0,1,"decision"),
 n("i7","invalid：返回逐行错误","文件名 / 行号 / code / message",0,2,"error",detail="修正原 CSV 内容需要新批次号重新上传；映射可在原工作区按最新 revision 再预检。当前没有编辑已上传 files 的接口。"),
 n("i8","ready：冻结待确认计划","保存 validated_hash；revision +1",1,2,"data",tables=["education_imports"]),
 n("i9","确认导入","仅 ready 或可重试 failed；版本匹配",2,2,"actor",api=["POST /api/v1/platform/education/imports/{id}/confirm"]),
],[e("i1","i2"),e("i2","i3","允许"),e("i3","i4"),e("i4","i5"),e("i5","i6"),e("i6","i7","有错误","error"),e("i6","i8","全部通过"),e("i8","i9")],refs=[src("imports","make_plan"),src("imports","preflight"),src("importer","build_import_plan")])
graph(s,"import-commit","03 · 后台事务、回执与失败回滚","业务表、staging 行和来源映射在同一事务内成功；确认后的任务可由 Worker 补偿领取。",[
 n("w1","确认 → running","先返回 HTTP 202；progress=0",0,0,"process"),
 n("w2","Worker 领取任务","学校锁 → 工作区行锁 skip_locked",1,0,"process",detail="API BackgroundTasks 启动执行；持久化任务可由 education_worker.py 恢复。只处理 running 任务。"),
 n("w3","再次预检与去重","复核引用；复用 CsvImportService",2,0,"decision"),
 n("w4","依赖顺序写入","学校 → 班级 → 学生 → 考试 → 学科",2,1,"data",tables=["schools","import_classes","students","exams","subjects"]),
 n("w5","三类成绩按键更新","总分 → 考试科目 / 学科分 → 小题分",1,1,"data",tables=["student_exam_scores","exam_subjects","student_subject_scores","question_scores"],detail="已有成绩按稳定业务键更新；原始排名和平均分来自文件，不自动重排全校排名。未提供的可选数值可能被更新为空，不是仅补空字段。"),
 n("w6","写入证据与回执","staging + 来源版本 + counts",0,1,"data",tables=["data_import_batches","data_import_rows","education_sources"]),
 n("w7","事务是否成功？","整批 commit 或 rollback",0,2,"decision"),
 n("w8","succeeded / 100%","回读数量、批次哈希、未绑定账号数",1,2,"outcome",detail="unbound_accounts 是当前学校全部未绑定学生数，不仅本次新增档案数。确认/重试成功批次返回原回执。"),
 n("w9","failed / 修复后重试","业务写入回滚；保留失败说明",0,3,"error",detail="再次预检失败时保存 issues；异常事务失败记录 IMPORT_TRANSACTION_FAILED。失败后只有 report.ok 仍为 true 的批次可直接确认重试，否则先重新预检。"),
 n("w10","新查询读取新成绩","分析 / 学情 / 问答；旧回答留快照",2,2,"outcome",target="lineage"),
],[e("w1","w2"),e("w2","w3"),e("w3","w4","通过"),e("w4","w5"),e("w5","w6"),e("w6","w7"),e("w7","w8","成功"),e("w7","w9","失败","error"),e("w8","w10")],refs=[src("imports","execute_import"),src("importer","apply_validated_plan"),src("importer","_upsert_domain")])
table(s,"文件名、必填字段、可选字段与落表",["输入文件","必填字段","可选字段","目标表 / 更新键"],[
["schools.csv","external_school_id, name, code","无","schools；code。工作台固定当前学校名称，不可借此重命名学校"],
["classes.csv","external_class_id, school_code, name","无","import_classes；school_id + external_class_id"],
["students.csv","external_student_id, school_code, student_no, name","external_class_id","students；school_id + external_student_id；不创建账号、不写 user_id"],
["exams.csv","external_exam_id, school_code, name, exam_type","start_date, end_date, academic_year, term","exams；school_id + external_exam_id"],
["subjects.csv","external_subject_id, school_code, code, name","无","subjects；school_id + code；绑定外部学科 ID"],
["student_exam_scores.csv","external_student_id, external_exam_id, school_code, total_score","full_score, class_rank, grade_rank, class_student_count, grade_student_count","student_exam_scores；student_id + exam_id"],
["student_subject_scores.csv","external_student_id, external_exam_id, external_subject_id, school_code, score, full_score","class_rank, grade_rank, class_avg, grade_avg","student_subject_scores；student_id + exam_id + subject_id；同时更新 exam_subjects"],
["question_scores.csv","external_student_id, external_exam_id, external_subject_id, school_code, question_no, score, full_score, lost_score","question_id, question_version_id, knowledge_point_id, answer_status","question_scores；student_id + exam_id + subject_id + question_no"],
])
note(s,"增删改的真实语义","新增批次与模板版本；映射在确认前可改；成绩更正通过新的有效批次按业务键更新。没有批次删除、成绩单行删除、已成功批次撤销或一键回滚接口。", "warn")
