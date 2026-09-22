s=section("support","09","原题、来源与反馈闭环","补充五个主模块依赖的题目版本、受控来源、订正与人工支持。",group="智能问答")
chain(s,"support-question","01 · 试卷原件 → 正式题目 → 得分依据","原题补全为错题复盘和知识点统计提供依据；六工具当前不自动读取题干。",[
 {"title":"上传试卷并绑定考试学科","text":"education_assets → papers / paper_versions","kind":"data","tables":["education_assets","education_papers","education_paper_versions"]},
 {"title":"框选区域并保存拆题草稿","text":"页码 + 归一化 x/y/width/height","kind":"data","tables":["education_paper_drafts"],"detail":"同一题可跨页、多区域；保存 expected_revision 防止覆盖；人工确认前仍是草稿。"},
 {"title":"可选 OCR 后人工核对","text":"Tesseract 中英文；结果不自动覆盖","kind":"process","tables":["education_ocr_jobs"],"detail":"queued→running→succeeded/failed；结果需人为应用。同修订最多5次重试；旧草稿结果不能套到新修订。"},
 {"title":"人工确认发布正式题目","text":"材料 / 大题 / 小题 / 独立题","kind":"data","tables":["education_questions","education_question_versions","education_question_tags","education_taxonomy"],"detail":"题干、选项、答案、解析、原件版本、区域、标签按正文版本保存。已发布草稿冻结；重复确认复用发布题目ID回执。"},
 {"title":"关联小题得分依据","text":"score_id → 正式 question_version_id","kind":"decision","api":["POST /api/v1/platform/education/scores/{id}/question"],"detail":"同校、同学科、已发布、题目未删除；绑定后不能静默改成其他版本。当前接口没有进一步验证题目所属试卷考试与得分考试相同。"},
 {"title":"统计 / 复盘可读该版本","text":"原题正文 + 标签 + 不可变来源","kind":"outcome","tables":["question_scores"],"target":"class-analysis"},
],refs=[src("curriculum","publish_draft"),src("school","link_score"),src("learning","question_facts")])
chain(s,"support-snapshot","02 · 受控旧资料快照 → 版本化来源","这里是按学校确认的快照接收，不是实时连接旧数据库。",[
 {"title":"提交受控 JSON 快照","text":"source_system / version / captured_at / records","kind":"actor","api":["POST /api/v1/platform/education/legacy-snapshots"]},
 {"title":"核对本校来源与水位","text":"旧 ID 保持字符串；时间不能倒退","kind":"decision","detail":"同来源实体同版本同哈希复用回执；同版本不同内容409。学生必须以 student_external_id 映射现有本校学生，不能按姓名猜测。"},
 {"title":"按依赖顺序投影","text":"考试 → 试卷 → 父题在前题目 → 报告 → 成绩","kind":"process"},
 {"title":"写业务实体与版本","text":"考试/题目稳定ID；报告版本独立ID","kind":"data","tables":["exams","education_papers","education_question_versions","diagnosis_reports"]},
 {"title":"保留不可变来源记录","text":"external_id / native_id / hash / payload","kind":"data","tables":["education_sources"],"detail":"唯一键：(school_id,source_system,entity_type,external_id,source_version)。报告版本独立 ID，以保持报告级权益。失败整批回滚。"},
 {"title":"查询来源与问答追溯","text":"学校来源工作台；消息 provenance","kind":"outcome"},
],refs=[src("legacy","ingest"),src("legacy_schema","Snapshot")])
chain(s,"support-review","03 · 本人错题 → 订正 → 复习记录","学生自评与客观得分分开，复习记录当前不自动写入模型记忆。",[
 {"title":"选择本人丢分小题","text":"question_scores.id；lost_score>0","kind":"actor"},
 {"title":"读取固定正式题目版本","text":"stem / options / answer / explanation","kind":"data","tables":["education_question_versions"],"detail":"无正式版本时仅显示分数事实和缺来源提示；父材料按不晚于子版本创建时间的正式版本回读。"},
 {"title":"加入复盘条目","text":"student_id + score_id 去重","kind":"data","tables":["education_reviews"],"api":["POST /api/v1/platform/education/student/reviews"]},
 {"title":"提交一次订正","text":"correction / mastery / next_review_at","kind":"actor","detail":"mastery=learning/reviewing/mastered；时间可空，提供时需时区。"},
 {"title":"追加独立历史记录","text":"旧订正保留；不覆盖原始得分","kind":"data","tables":["education_review_records"]},
 {"title":"回读最新自评状态","text":"mastery_source=student_self_report","kind":"outcome","detail":"没有复习条目或记录的删除/编辑接口；没有AI自动批改、自动判定掌握、自动注入问答上下文。"},
],refs=[src("learning","question_facts"),src("learning","add_review"),src("learning","add_review_record")])
graph(s,"support-feedback","04 · 回答反馈与人工服务分支","两类记录由明确用户操作建立；Guard 并不会自动创建风险或转接。",[
 n("f1","学生收到回答","assistant message_id / session_id",1,0,"actor"),
 n("f2","评价该回答","helpful / not_helpful / data_wrong / inappropriate",0,1,"actor",api=["POST /api/v1/chat/messages/{message_id}/feedback"]),
 n("f3","请求人工帮助","reason / summary / 可选 session_id",2,1,"actor",api=["POST /api/v1/platform/student/handoffs"]),
 n("f4","验证本人消息并保存反馈","同回答已有反馈时同内容幂等，异内容409",0,2,"data",tables=["platform_feedback","audit_logs"]),
 n("f5","保存 open 工单","绑定本人学生与可选会话",2,2,"data",tables=["human_handoffs"]),
 n("f6","管理侧处理反馈","open → acknowledged → resolved / closed",0,3,"process",detail="按允许状态图、expected_version 和处理说明执行；不是任意改状态。若数据有误，需另到源模块更正，不自动改成绩。"),
 n("f7","接单、回复、解决","open → accepted → resolved；双方消息",2,3,"process",tables=["education_handoff_messages"],detail="回复时核验本校/任教/本人归属；管理人员须为接单人或学校管理员；QA只读。解决/关闭/重开需真实说明。"),
 n("f8","学生回读与确认","查看处理结果；确认关闭或带原因重开",1,4,"outcome",detail="重开清空分配人及接单/解决时间；状态版本并发保护。没有反馈/工单物理删除接口，也不自动训练模型。"),
],[e("f1","f2","反馈"),e("f1","f3","人工帮助"),e("f2","f4"),e("f3","f5"),e("f4","f6"),e("f5","f7"),e("f6","f8"),e("f7","f8")],refs=[src("chat","submit_feedback"),src("platform","create_student_handoff"),src("workflow","transition_workflow"),src("learning","handoff_reply")])

s=section("crud","10","增删改查总矩阵","将“可修改”“新增版本”“软停用”“没有接口”分开，防止混淆。",group="数据与边界")
table(s,"各对象完整操作矩阵",["对象","增 Create","查 Read","改 Update","删 Delete / 停用 / 替代","影响与约束"],[
["班级 import_classes","原生创建 / CSV upsert","列表、名称搜索、分页","原生 name/status","inactive；无硬删除","active学生或任教引用时不可停用"],
["学生 students","原生档案 / CSV upsert","教务目录、学情明细","原生 class_id/status；账号单独绑定","inactive；无硬删除/解绑","按ID区分人；历史成绩保留"],
["教师 users","本模块不提供账号开通","已有本校教师目录","display_name/status","inactive；无硬删除","角色来自既有身份系统"],
["任教 teaching_assignments","教师×班级×科目授权","任教关系与有效选项","关系字段、有效时间、status","inactive；无DELETE","变动影响下次教师读数"],
["学科 subjects","原生创建 / CSV upsert","列表 / 搜索","无原生编辑API；CSV可更新","无删除/停用API","名称是工具科目匹配输入"],
["考试 exams","原生创建 / CSV / 快照","列表、考试科目详情","原生元数据/status；来源更新","inactive；无DELETE","查询未普遍过滤inactive"],
["考试科目 exam_subjects","配置科目满分 / 导入","随考试详情读取","教务编辑有成绩引用阻断","无移除科目API","导入满分路径校验不完全同教务"],
["导入工作区 education_imports","上传新批次","列表、预检/事务回执","确认前mapping+revision","无删除、撤销、成功回滚API","改文件需新批次号"],
["列映射模板","按name新增version","模板列表","保存等于新增版本","无删除API","旧模板版本保留"],
["总分 student_exam_scores","导入 / 受控快照","页面 / Tool / 依据","新批次按student+exam更新","无单行DELETE","不自动由学科求和或重排排名"],
["学科 student_subject_scores","导入 / 受控快照","页面 / Tool / 依据","按student+exam+subject更新","无单行DELETE","得分率/均分差由代码计算"],
["小题 question_scores","导入 / 受控快照","小题丢分 / 依据 / 复盘","业务键更新；固定题目版本一次绑定","无单行DELETE","不得静默更换题目依据"],
["班级分析结果","请求时计算","按班级×学科×考试","改查询或更正事实源","无结果实体可删除","写读取审计，不回写成绩"],
["学生学情结果","请求时组装","目录、学科/总分/小题详情","更正教务或成绩源","无结果实体可删除","目录筛选active；分析样本不同"],
["正式报告 diagnosis_reports","新增独立报告版本","本校列表 / 本人授权报告","不覆盖旧版；新增版本替代","无删除/下架API","新增不自动授予权益"],
["原件 education_assets","上传有效PDF/PNG/JPEG","受权内容 / 页图","不可变；替换即新附件","无删除API","报告附件用途独占"],
["报告附件关系","随报告创建固定","版本列表及受权打开","无替换绑定API","无解绑API","报告版本固定asset_id"],
["权益 student_entitlements","模型存在；本模块无开通API","每次报告读取核验","本模块无变更API","本模块无撤销API","不能把数据库字段当作已交付功能"],
["题库正式题目","原生创建 / 拆题发布 / 快照","目录 / 正式版本详情","新增正文版本；外部来源只读","批量软删/恢复，逐项引用检查","得分/复盘/标签/子题等引用限制"],
["知识点与标签","新增同科树节点","树 / 题目关联","revision校验后更新","软删/恢复；引用阻断","名称修改可能影响以后统计标签"],
["复盘与订正","新增条目；追加订正记录","本人条目与历史","追加记录作为状态变化","无编辑/删除API","自评状态不自动回传Agent"],
["会话 chat_sessions","创建本人会话","本人active列表","只提供考试/学科范围变更","DELETE是归档；无恢复API","消息与追踪不硬删"],
["消息 chat_messages","用户/助手各保存记录","本人会话历史","无已完成内容编辑API","异常清理未完成用户行；无用户删除API","sources与selected_context固定"],
["反馈 / 人工工单","用户明确提交","本人/授权管理队列","受控状态流转、追加人工消息","无物理删除API","不自动更改事实源或训练模型"],
])
chain(s,"crud-control","写入操作共同约束","下面是检查项的逻辑顺序；不同接口只采用其中适用的机制，具体以接口契约为准。",[
 ["当前数据库身份","账号有效、真实角色、本校范围","decision"],
 ["对象归属与来源","owned；外部来源不可原生编辑","decision"],
 ["引用 / 版本 / 幂等校验","冲突返回409；禁止静默覆盖","decision"],
 ["业务写入与审计","事务内保存对象及回执","data"],
 ["提交后重新读取","呈现服务端实际结果","outcome"],
 ["后续读者重新过滤","教师任教、本人身份、报告权益","decision"],
],refs=[src("common"),src("education","write")])

s=section("lineage","11","数据血缘与修改影响","哪些写入会改变下一次分析，哪些历史材料保持不变。",group="数据与边界")
chain(s,"lineage-score","01 · 一条成绩从文件到回答的血缘","以下是结构示例，不是实际学生数据：某学生 / 某次数学考试 / 第12题。",[
 {"title":"question_scores.csv 的一行","text":"外部学生 / 考试 / 科目 / question_no","kind":"actor"},
 {"title":"映射与预检计划","text":"文件名、原行号、row_hash、raw_data","kind":"data","tables":["data_import_rows"]},
 {"title":"解析成本校内部 ID","text":"student_id / exam_id / subject_id","kind":"data","tables":["students","exams","subjects"]},
 {"title":"更新固定业务键成绩","text":"score / full_score / lost_score","kind":"data","tables":["question_scores"]},
 {"title":"保留来源映射","text":"native_id + 批次source_version + 哈希","kind":"data","tables":["education_sources"]},
 {"title":"get_question_losses 取数","text":"本人范围、学科、考试、TOP N","kind":"process"},
 {"title":"生成答案并固化依据","text":"facts + provenance + selected_context","kind":"data","tables":["chat_messages"]},
 {"title":"打开依据，校验本人范围","text":"显示生成时捕获的分数与来源版本","kind":"outcome"},
 {"title":"后续新批次修正原始分数","text":"新问答读新值；旧消息不自动改写","kind":"outcome"},
],refs=[src("imports","execute_import"),src("analysis_tool","GetQuestionLossTool"),src("learning","pin_sources")])
table(s,"数据变更影响矩阵",["触发变更","下一次页面查询","下一轮问答","已保存历史","注意点"],[
["新批次更新分数","班级/学情重新查询反映新值","Tool查询更新后的事实","旧答案与sources保持","不是自动重算所有旧答案"],
["学生转班","新班级统计、教师范围变化","本人历史成绩仍依student_id","历史记录保留","班级分析使用当前归属，历史班级不能准确复现"],
["学生档案停用","目录不显示active以外学生","get_current_student拒绝","成绩报告会话保留","班级分析未额外过滤学生状态"],
["教师停用/任教到期","下次认证或范围查询拒绝","学生问答不因此变成教师权限","原任教记录保留","角色组合判定优先级需看后端"],
["考试停用或日期更改","列表状态/排序可能变化","默认考试或趋势截止可能变化","旧selected_context ID仍在","inactive没有被所有查询过滤"],
["新增报告正式版本","学校与已授权版本列表更新","工具可能选取时间最新获授权报告","旧报告ID/原件保留","报告级授权不自动覆盖新报告ID"],
["报告权益撤销/到期","新报告与原件访问拒绝","get_diagnosis重新查授权","旧sources仍存储","历史消息回读没有逐引用重新查权益"],
["题目新版本/知识点更名","新题详情/未来聚合标签变化","小题工具仍只读分数事实","已固定question_version_id不换","正文版本固定不等于全部关联名称快照化"],
["归档会话","active会话列表不再显示","该会话不可继续发送","数据库消息与审计保留","当前无恢复入口"],
])

s=section("data","12","完整数据字典","从当前 SQLAlchemy 模型提取真实表名、字段名、类型、空值约束与关系约束。",group="数据与边界",special="data")
note(s,"字典解读","字段存在不代表已在界面开放；例如权益开通、报告下架、模型费用等仍需核对写入路径。所有字段只展示结构和代码默认值，不展示真实数据或凭据。")
DATA["tableInfo"]={
"schools":["学校","教务/导入的租户边界；school_id来源","身份范围，不把学校全量数据送模型"],
"users":["登录用户与教师账号","既有身份系统；教师页修改显示名/状态","只用于认证；密码哈希不进入Prompt"],
"roles":["角色字典","既有身份角色定义","判定STUDENT / TEACHER / SCHOOL_ADMIN等"],
"user_roles":["用户角色关系","关联用户、角色、学校","每次认证重新读取"],
"students":["学生档案","教务原生/CSV；user_id单独绑定","ContextBuilder的姓名、本人ID、班级范围"],
"import_classes":["班级及外部映射","教务原生/CSV","教师范围、班级分析；不是学生Tool的数据结果"],
"teaching_assignments":["教师任教授权","教务教师任教页","管理侧访问，不开放其他学生给学生问答"],
"exams":["考试档案","教务/CSV/受控快照","考试名称、日期、选择与趋势"],
"subjects":["学科字典","教务/CSV","subject_name解析及学科筛选"],
"exam_subjects":["考试科目与满分","教务配置/学科成绩导入","计算口径配置；Tool主要读取成绩行满分"],
"student_exam_scores":["学生考试总分","总分CSV/受控快照","总分、排名、人数、趋势、上下文"],
"student_subject_scores":["学生学科成绩","学科CSV/受控快照","得分率、排名、均分差、学科趋势"],
"question_scores":["学生小题得分","小题CSV/受控快照","题号、得分、满分、丢分、答题状态"],
"diagnosis_reports":["正式诊断/成绩/批阅报告","报告工作台/受控快照","get_diagnosis读取structured_json，原文另受权读"],
"student_entitlements":["学生资源权益","已有授权数据；这五模块无写接口","报告读取实时校验"],
"education_assets":["私有原件","经校验的PDF/PNG/JPEG上传","不直接输入模型；受权浏览"],
"education_report_attachments":["正式报告原件关联","报告创建或快照","报告版本原件定位"],
"education_sources":["来源版本记录","CSV成功写入/受控快照","provenance:版本、哈希、水位"],
"education_imports":["CSV导入工作区","上传、映射、预检、确认","上游生产；不直接输入模型"],
"education_mapping_templates":["列映射模板版本","保存模板新增版本","上游导入辅助"],
"data_import_batches":["导入事务批次","CsvImportService","回执、校验和错误追踪"],
"data_import_rows":["原始导入暂存行","CsvImportService staging","原行号与行哈希审计"],
"education_papers":["试卷档案","试卷工作台/快照","考试学科原件关联；非六工具正文来源"],
"education_paper_versions":["试卷原件版本","上传替换新增版本","固定原件而不覆盖"],
"education_paper_drafts":["拆题草稿","人工框选、OCR应用、修订保存","人工发布前不作正式题目"],
"education_ocr_jobs":["OCR任务","受确认的本地Tesseract任务","结果需人工应用；不是问答模型"],
"education_questions":["题目身份与层级","题库/拆题/快照","原题复盘与知识点统计的关联身份"],
"education_question_versions":["题干答案解析版本","题库版本化写入","固定版本原题阅读；目前不进六工具正文"],
"education_taxonomy":["知识点与其他标签树","题库维护","班级知识点聚合；学生工具不自动做掌握诊断"],
"education_question_tags":["题目版本标签关系","题目保存/发布","标签映射补全"],
"education_reviews":["本人复盘条目","学生主动加入","不自动进入模型记忆"],
"education_review_records":["订正与自评历史","每次复习追加","student_self_report；不覆写考试分数"],
"chat_sessions":["学生会话","创建/选范围/归档","考试学科范围与并发版本"],
"chat_messages":["消息及固定依据","用户请求、助手最终回答","content/sources/selected_context为回读核心"],
"agent_runs":["问答运行","AgentLoop创建与完成","意图、Prompt版本、Guard、状态"],
"tool_call_logs":["工具运行日志","执行每个确定性Tool","输入参数和事实返回摘要"],
"model_usage_logs":["模型用量","AgentLoop模型完成后","模型、token计数和延迟；不等于全部费用字段已写"],
"prompt_templates":["提示词模板","全局Prompt注册与发布","student_qa_system版本化渲染"],
"audit_logs":["访问与变更审计","认证范围内业务读写","resource_id / action / allowed / metadata；追溯"],
"operation_receipts":["幂等操作回执","claim()","避免重复业务提交"],
"platform_feedback":["反馈运营","学生回答评价/支持页反馈","人工处理闭环；非自动模型训练"],
"human_handoffs":["人工工单","学生主动发起","会话关联与状态流转"],
"education_handoff_messages":["人工服务消息","学生/处理人员追加","双方消息回读；不注入Agent历史"],
"risk_events":["风险事件","管理侧创建/既有事件","学情目录风险计数；Guard不会自动写入"],
"knowledge_documents":["知识文档","管理侧审核发布","当前无RAG接入"],
"parent_authorizations":["家长授权请求","学生支持与家长确认","独立支持流程；不等于DIAGNOSIS权益"],
"revoked_tokens":["已撤销令牌","认证安全流程","令牌验证边界"],
}
DATA["fieldLabels"]={"id":"内部唯一标识","school_id":"学校/租户ID","student_id":"学生ID","user_id":"登录用户ID","exam_id":"考试ID","subject_id":"学科ID","class_id":"当前班级ID","source_system":"来源系统","created_at":"创建时间","updated_at":"更新时间","status":"状态","name":"名称","code":"代码","external_id":"外部原始标识","native_id":"新系统实体ID","source_version":"来源版本","content_hash":"内容SHA-256","captured_at":"来源采集水位","payload":"保留的来源字段","revision":"修订号","version":"版本","content":"内容/私有二进制，具体见类型","files":"上传文件名到CSV文本","mapping":"目标字段到源列映射","report":"预检/执行回执","batch_key":"工作台批次编号","created_by":"创建人","progress":"真实进度","filename":"原文件名","media_type":"已校验MIME","byte_size":"文件字节数","storage_key":"稳定私有存储键","pages":"页码与尺寸","paper_id":"试卷ID","asset_id":"私有原件ID","number":"版本序号","source_id":"来源版本ID","parent_id":"父对象ID","kind":"对象种类","title":"标题","deleted_at":"软删除时间","question_id":"稳定题目ID","question_version_id":"固定正式题目版本ID","stem":"题干/材料正文","options":"选项数组","answer":"参考答案","explanation":"解析","paper_version_id":"固定试卷原件版本","regions":"页码及归一化区域","published_at":"正式发布时间","node_id":"标签/知识点节点ID","entries":"结构化草稿条目","published_revision":"已发布草稿修订","published_ids":"发布题目ID回执","draft_id":"草稿ID","draft_revision":"OCR所用草稿修订","input_entries":"OCR输入快照","attempt":"尝试次数","result":"OCR识别结果","error_code":"稳定错误码","lease_until":"任务租约截止","finished_at":"完成时间","report_id":"正式报告ID","score_id":"小题得分记录ID","review_id":"复盘条目ID","correction":"学生订正笔记","mastery":"学生自评掌握状态","next_review_at":"下次复习时间","handoff_id":"人工工单ID","sender_id":"发送人ID","sender_role":"学生/工作人员","request_hash":"幂等请求哈希","payload_hash":"请求内容哈希","resource_id":"目标资源ID","metadata":"附加审计字段（ORM extra_data）"}

s=section("permissions","13","角色、数据范围与授权条件","按当前路由、认证依赖和查询条件说明，单独列出源码中的策略差异。",group="数据与边界")
table(s,"入口权限矩阵",["能力","学生","教师","学校管理员","QA","市级 / 超管"],[
["师生教务写入","无","无","本校写","只读","普通市级无；超管当前学校写"],
["教务任教相关选项","本人会话选项另查","当前有效任教相关","本校","本校读","education中普通市级不开放"],
["成绩导入 / 原件 / 报告管理","无","无","本校写","本校读","普通市级无；超管当前学校"],
["班级分析","无","同班级×同学科有效任教","本校","本校读","普通市级无；超管本校"],
["管理学情列表与详情","无","所授班级学科；无总分","本校全科","本校读","后端CITY_OPERATOR/SUPER_ADMIN可跨校查询，见下方差异"],
["学生问答 / 复盘","本人active档案","无学生角色则拒绝","无学生角色则拒绝","无学生角色则拒绝","并非自动获得学生能力"],
["学生报告 / 原件","本人正式报告+匹配权益","无报告原件权限","本校管理读取","本校管理读取","education附件一般市级无；超管本校"],
["反馈 / 人工队列","本人回读/补充","任教学生范围；接单回复","本校处理","只读","按平台管理范围策略"],
])
chain(s,"permission-path","学生问答与管理学情的权限检查顺序","权限放在数据库查询和资源入口；Prompt不承担授权。",[
 ["验证访问令牌","有效签名、类型、撤销状态","decision"],
 ["重读账号与数据库角色","users.status=active；真实学校/角色","decision"],
 ["选择业务访问分支","学生本人 / 学校管理 / 教师任教","decision"],
 ["按资源追加范围","student_id / school_id / class×subject","decision"],
 ["报告再查资源级权益","产品、状态、有效期、资源类型与ID","decision"],
 ["读取并记录必要审计","新请求重新校验；拒绝也记录报告审计","outcome"],
],refs=[src("auth"),src("scope"),src("grants")])
note(s,"当前代码的市级明细差异","management_details 和 management_students 允许 CITY_OPERATOR；access_scope.scoped() 对市级/超管直接返回未加学校过滤的 query。因而后端存在跨校学情读取能力，即使市级菜单未提供学生详情入口。不能只根据菜单或产品文档断言市级仅能看汇总。", "warn")

s=section("gaps","14","已发现的边界与实现差异","这里记录源码阅读所见，未对业务代码作修改；不把设计意图当成已验证行为。",group="核对与追溯",special="gaps")
DATA["gaps"]=[
["部分默认考试排序不一致","考试概览/科目/丢分和默认排名比较按 StudentExamScore.created_at；ContextBuilder、趋势、学情目录多按考试日期。补导历史成绩后可能出现“最近考试”不同。",src("exam_tool","GetExamSummaryTool")],
["空满分仍有150回退","get_exam_summary 在 full_score 为假值时返回150.0；ContextBuilder和部分页面把缺满分保留为未知。图谱按实际分支描述，未把该默认值当成真实学校满分。",src("exam_tool","GetExamSummaryTool")],
["诊断工具没有落实施加学科过滤","Agent会传subject_name，但GetDiagnosisTool仅按授权与可选exam_id查询；也没有固定report_type=diagnosis。可能选到同考试其他类型或学科的已授权报告。",src("analysis_tool","GetDiagnosisTool")],
["BASIC诊断措辞只警告","Guard将诊断性措辞判为warn，原答案不改写；真正报告访问仍由Tool数据库授权阻断。不能宣称所有越界诊断表达都被强制挡住。",src("guard","_decide_action")],
["最近/上次实体未完整接通","IntentRouter提取exam_reference，但_tool_args未使用；比较工具能自行找前次，不代表所有含“上次”的问题都定位上次考试。",src("agent","_tool_args")],
["只有一次确定性工具选择","每轮suggested_tools[:1]且tools=None；没有多工具自主规划、任意数据库访问或跨模块自动写入。复合问题可能只命中第一类意图。",src("agent","run")],
["事件时序不是实时逐Token","主链路完成Agent和Guard后才补发工具事件、来源与整段content_delta。不能把SSE连接等同于逐Token模型生成。",src("chat","stream_message")],
["导入与教务满分保护不同","教务改变已有学科满分会查成绩引用；CSV写入器可更新exam_subjects.full_score，预检仅校验同批次一致，未见跨批次历史一致性检查。",src("importer","_upsert_domain")],
["历史回答回读与撤权策略不同","evidence打开时重新查报告权益，但历史messages及已完成请求重放直接返回已保存sources。撤权后历史sources中的报告摘要仍可能回读。",src("chat","get_session_messages")],
["固定证据是取数后的再次读取","pin_sources在模型和Guard之后重新查业务行与最新SourceRecord；并发导入期间，未见保证工具结果与固定证据使用同一数据库快照的控制。",src("learning","pin_sources")],
["班级历史没有考试时名单快照","当前class_id优先，否则external_class_id；转班会改变历史考试班级聚合。分析查询也未额外过滤学生active，与学情目录样本策略不同。",src("school","class_analysis")],
["停用考试不等于全链路隐藏","考试有active/inactive，但多处会话选项、上下文和工具查询未按该状态过滤；不能将停用画成全局删除或自动拒读。",src("chat","get_session_context")],
["排名对比缺少可比性判定","get_rank_change直接求分差/名次差，没有像班级均分对比那样先核对满分一致，也未证明两次参与人群一致。",src("score_tool","GetRankingChangeTool")],
["零平均分与Top N口径","学科Tool对class_avg/grade_avg用真值判断，0可能显示为空；小题total_lost_score仅返回的TOP N相加，默认min_loss=0可含零丢分项。",src("analysis_tool","GetQuestionLossTool")],
["市级API能力大于菜单展示","管理学情后端允许CITY_OPERATOR，scoped的市级分支不加学校过滤；应与“市级只看汇总”的产品预期单独核对。",src("scope","scoped")],
["题库/文档/复习尚未成为问答检索","正式原题正文、knowledge_documents、订正记录、人工消息、班级分析结果均未被六工具直接检索并注入本轮模型。",src("agent","run")],
["缺少若干生命周期入口","学科编辑/删除、报告下架/删除、导入撤销、学生解绑、报告权益管理不在这五模块当前API中。字典有字段不等于功能已开放。",src("education")],
]

s=section("sources","15","接口与源码核对","接口清单由路由装饰器提取；每个源码位置包含当前内容哈希与可展开片段。",group="核对与追溯",special="sources")
note(s,"证据层级","HTML是当前工作区静态代码说明，含源码中已存在的增量实现；不是生产部署验收报告。接口前缀以 /api/v1 展示。引用可在HTML里展开阅读，文件链接需保留仓库相对目录。")
