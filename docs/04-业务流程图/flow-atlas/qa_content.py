s=section("chat","07","智能问答的完整执行链路","从身份到会话、取数、模型、审核、事件、存档、重试与来源回读。",group="智能问答",route="/chat")
graph(s,"chat-entry","01 · 身份 → 会话 → 范围 → 消息幂等","所有本人标识由服务端认证构造；页面不能指定别人的 student_id。",[
 n("q1","学生打开智能问答","Bearer access token；读取本人角色",0,0,"actor"),
 n("q2","认证用户与学生档案","users active + STUDENT + students active",1,0,"decision",detail="JWT 验证后重读数据库账号与角色；通过 students.user_id、school_id 找本人。账号未绑定或学生停用时无法进入数据问答。",tables=["users","roles","user_roles","students"]),
 n("q3","创建 / 读取本人会话","chat_sessions.status=active",2,0,"data",tables=["chat_sessions"],api=["POST /api/v1/chat/sessions","GET /api/v1/chat/sessions"]),
 n("q4","选择考试与学科","选项来自本人总分 / 学科成绩",2,1,"actor",api=["GET /api/v1/chat/sessions/{session_id}/context"]),
 n("q5","校验范围及版本","已有本人分数；expected_version 一致",1,1,"decision",detail="有未关联运行的用户消息则 MESSAGE_IN_PROGRESS，不允许切换。考试选项依赖 StudentExamScore；只导入学科分仍可能无法选择考试。"),
 n("q6","保存选中范围","selected_exam_id / subject_id / version+1",0,1,"data",tables=["chat_sessions"],api=["PUT /api/v1/chat/sessions/{session_id}/context"]),
 n("q7","发送消息","content 1–4000 字符 + client_message_id",0,2,"actor",api=["POST /api/v1/chat/sessions/{session_id}/stream","POST /api/v1/chat/sessions/{session_id}/messages"]),
 n("q8","同 ID 的请求已存在？","同会话、同内容、用户消息才可复用",1,2,"decision"),
 n("q9","重复请求分支","已完成重放；处理中拒绝；异内容冲突",2,2,"outcome",detail="已完成返回保存的答案和 sources；未完成 MESSAGE_IN_PROGRESS；client_message_id 用于不同内容或会话时 CLIENT_MESSAGE_ID_CONFLICT。"),
 n("q10","保存新的用户消息","固化 selected_context；准备历史",1,3,"data",tables=["chat_messages"],detail="行锁保护会话；保存 exam_id、subject_id、context_version。历史查询最近20条，Agent 实际使用传入历史末6条。"),
],[e("q1","q2"),e("q2","q3"),e("q3","q4"),e("q4","q5"),e("q5","q6","验证通过"),e("q6","q7"),e("q7","q8"),e("q8","q9","存在"),e("q8","q10","新消息")],refs=[src("auth","get_current_student"),src("chat","set_session_context"),src("chat","_save_user_message"),src("chat","_find_idempotent_reply")])
chain(s,"chat-agent","02 · 上下文 → 意图 → Tool → Prompt → 模型","这是有限的一轮确定性取数；模型调用参数 tools=None。",[
 {"title":"动态构建本人上下文","text":"姓名 / 身份 / 权益 / 最近最多5次总分","kind":"data","tables":["students","student_entitlements","student_exam_scores","exams"],"detail":"选考试时按所选日期截断；优先置顶选中考试。有选定学科时移除上下文中的总分等事实，只保留考试 ID/名称/日期，避免混用。"},
 {"title":"规则识别意图与科目","text":"六类意图按顺序；无匹配 general_chat","kind":"decision","detail":"多个正则命中取第一个意图；支持9门固定中文科目名。提取的 exam_reference 目前没有被 _tool_args 转为上一次考试 ID。","target":"routing"},
 {"title":"选定范围覆盖实体","text":"session exam_id / subject_name 优先","detail":"用户已选择学科且意图为考试概览时，将 get_exam_summary 改为 get_subject_scores。上下文和 Tool 参数从服务端会话提供。"},
 {"title":"建立 agent_runs","text":"query / intent / entitlement / running","kind":"data","tables":["agent_runs"]},
 {"title":"最多执行一个数据工具","text":"ToolContext 强制 school_id / student_id","detail":"从 suggested_tools[:1] 取工具；未命中意图时无工具。工具失败转为 ok=false 和错误码，模型说明限制；不会自动改查其他学生。","target":"routing"},
 {"title":"保存工具执行记录","text":"参数 / 返回摘要 / 状态 / 错误码","kind":"data","tables":["tool_call_logs"],"detail":"sources 从 ToolResult.evidence 收集；tool_call_count 为实际调用次数。"},
 {"title":"读取版本化系统提示词","text":"student_qa_system；缺失用内置模板","kind":"data","tables":["prompt_templates"],"detail":"保存具体 prompt_version；模板数据库错误也使用内置安全提示词。"},
 {"title":"拼接模型输入","text":"系统 + 历史末6条 + 问题 + TOOL_RESULT","detail":"工具结果作为 system 内容加入；只加入 result.data 或 error_code，不传数据库连接、不传管理写入接口。"},
 {"title":"ModelGateway.chat","text":"temperature=0.2；默认超时30秒","detail":"按配置使用 DeepSeek / OpenAI-compatible；fake 仅在显式配置时启用。无可用 Provider 返回错误。主链路调用 chat 而非 gateway.stream。"},
 {"title":"记录模型用量","text":"provider / model / tokens / latency_ms","kind":"data","tables":["model_usage_logs"]},
 {"title":"ResponseGuard 审核","text":"数字 / BASIC措辞 / 隐私 / 逻辑","kind":"decision","target":"gaps"},
 {"title":"完成或失败运行记录","text":"completed / failed + guard_action","kind":"outcome","tables":["agent_runs"],"detail":"通过返回最终答案、steps、sources；异常写 AGENT_FAILED。运行层不自动创建风险事件或人工工单。"},
],refs=[src("agent","run"),src("agent","_build_messages"),src("context","build_context"),src("gateway","chat")])
graph(s,"chat-guard","03 · 响应检查与展示策略","Guard 是启发式规则；不能当成完整的事实证明。",[
 n("g1","模型候选回答","answer + Context + Tool 数值集",1,0,"process"),
 n("g2","执行四类规则检查","分数来源 / 权益措辞 / 人名 / 矛盾",1,1,"decision",detail="数字规则主要匹配“数字+分”（0–1000），允许<0.5误差和简单绝对差；隐私基于中文姓名+同学/学生；不能覆盖全部语义、排名、百分比。"),
 n("g3","pass","无问题：原答案通过",0,2,"outcome"),
 n("g4","warn","诊断性措辞 / 矛盾：记录并放行",1,2,"decision",detail="BASIC 下命中诊断性措辞当前是 warn，原文仍可展示，不是硬阻断；不自动改写答案。"),
 n("g5","block","疑似捏造 / 他人隐私 / 分数超范围",2,2,"error",detail="替换为固定核实提示：“这个回答包含无法确认或不适合直接展示的信息，请联系老师核实。”不是自动转人工。"),
 n("g6","保存 Guard 结论","agent_runs.guard_action；日志记录 issues",1,3,"data",tables=["agent_runs"]),
 n("g7","进入最终事件与消息保存","通过审核的整段答案 / 固定替代文案",1,4,"outcome"),
],[e("g1","g2"),e("g2","g3","无问题"),e("g2","g4","中等规则命中"),e("g2","g5","高风险规则命中","error"),e("g3","g6"),e("g4","g6"),e("g5","g6"),e("g6","g7")],refs=[src("guard","validate"),src("guard","_decide_action"),src("agent","run")])
chain(s,"chat-stream","04 · SSE、持久化、取消与重试","事件流存在，但正文在模型与审核完成后整段下发。",[
 {"title":"message_start","text":"session_id / message_id；request_id / seq"},
 {"title":"等待 Agent 完整返回","text":"取数 + 模型 + Guard + pin_sources","detail":"当前 tool_call_start/end 也是在 Agent 返回后按 steps 补发，不能把它们描述为工具开始执行的实时通知。"},
 {"title":"工具与来源事件","text":"tool_call_start/end → source × N","detail":"新请求：先工具事件、再来源、再正文；历史重放分支先正文再来源。每个 SSE 事件携带 request_id、seq。"},
 {"title":"content_delta","text":"一次发送完整 final_answer","kind":"outcome","detail":"这是审核后整段输出，不是逐 Token。前端安全 Markdown / 公式禁用原始HTML、外部图片和模型链接导航。"},
 {"title":"保存助手消息并关联运行","text":"content / agent_run_id / sources / context","kind":"data","tables":["chat_messages"]},
 {"title":"message_end → done","text":"返回最终助手 message_id 与运行 ID","kind":"outcome"},
 {"title":"错误 / 网络取消分支","text":"回滚未完成写入；删除未完成用户行","kind":"error","detail":"异常返回 CHAT_FAILED 或 MODEL_PROVIDER_NOT_CONFIGURED；取消通过 CancelledError 清理尚未提交的关联用户行。已提交助手消息不删除。"},
 {"title":"按相同 client ID 重试","text":"完成则重放；失败清理后可重新执行","kind":"decision","detail":"重放保存的 sources，不重新用当前分数伪造旧依据。已完成回复中的 tools_called 回执可能为0，不代表原运行没有工具。"},
 {"title":"会话归档","text":"DELETE 仅设 status=archived","kind":"data","tables":["chat_sessions"],"api":["DELETE /api/v1/chat/sessions/{session_id}"],"detail":"没有会话恢复、重命名、单条消息编辑/删除接口；归档保留历史消息与审计。"},
],refs=[src("chat","stream_message"),src("chat","archive_session"),src("stream_ui"),src("answer_ui")],note="最后三项说明异常与生命周期分支，不表示每次成功回答都要发生错误或归档。")
chain(s,"chat-evidence","05 · 来源事实固化与再次打开","来源卡是回答时保存的事实和版本；阅读时重新校验访问权限。",[
 {"title":"ToolResult.evidence","text":"type / resource_id / label / as_of","kind":"data"},
 {"title":"pin_sources 查本人记录","text":"分数 / 报告分别按范围校验","kind":"decision","detail":"分数：本校本人；报告：require_report 再查有效权益。"},
 {"title":"固定事实 facts","text":"得分 / 排名 / 题号或 report_version","kind":"data","detail":"总分：total_score/full_score/class_rank/grade_rank；学科：score/full_score/class_rank/grade_rank；小题：score/full_score/lost_score/question_no/question_version_id；报告：version/generated_at/summary。"},
 {"title":"记录来源 provenance","text":"source_system / source_version / hash / 水位","kind":"data","tables":["education_sources"],"detail":"取 native_id 的最新 SourceRecord；没有来源映射时回退 native + updated_at。此为取数后再读取进行固化，并非已证明与工具查询处于同一快照。"},
 {"title":"写 chat_messages.sources","text":"历史消息 / 重试均返回这份快照","kind":"data","tables":["chat_messages"]},
 {"title":"学生点击依据卡","text":"/evidence/{message_id}/{index}","kind":"actor","api":["GET /api/v1/platform/education/evidence/{message_id}/{index}"],"detail":"当前 MessageBubble 只直接展示前4条依据；完整来源仍在消息中。"},
 {"title":"重新鉴权与引用定位","text":"本人助手消息；索引有效；权益仍有效","kind":"decision"},
 {"title":"回读 captured_source","text":"显示生成时事实；记录 evidence.read","kind":"outcome","tables":["audit_logs"]},
 {"title":"权限已撤销或范围错误","text":"拒绝再次打开，不伪造当前依据","kind":"error","detail":"历史消息的普通回读接口仍直接返回已保存 sources；撤权后是否隐藏其中报告摘要，当前与 evidence 接口的策略不完全一致，见差异清单。"},
],refs=[src("learning","pin_sources"),src("learning","evidence"),src("bubble_ui")],note="末项是鉴权失败分支。历史 sources 的回读与依据下钻权限存在差异，页面明确展示现状。")

s=section("routing","08","六个工具与问题逐项对应","按真实规则顺序、实际查询字段、计算公式与失败条件说明。",group="智能问答")
graph(s,"tool-routing","01 · 规则匹配与工具选择","按下表顺序取第一个匹配意图；每轮最多一个 Tool。",[
 n("t0","问题 + 会话所选范围","自然语言关键词；考试/科目可选",1,0,"actor"),
 n("t1","总分 / 考得如何","exam_summary → get_exam_summary",0,1,"process",tables=["student_exam_scores","exams"]),
 n("t2","各科 / 数学多少分","subject_scores → get_subject_scores",1,1,"process",tables=["student_subject_scores","subjects"]),
 n("t3","排名变化 / 比上次","ranking_change → get_rank_change",2,1,"process",tables=["student_exam_scores","student_subject_scores"]),
 n("t4","趋势 / 走势","score_trend → get_score_trend",0,2,"process",tables=["student_exam_scores","student_subject_scores","exams"]),
 n("t5","哪题丢分 / 失分最多","question_loss → get_question_losses",1,2,"process",tables=["question_scores","subjects"]),
 n("t6","诊断 / 如何提高","diagnosis → get_diagnosis",2,2,"process",tables=["diagnosis_reports","student_entitlements"]),
 n("t7","无正则命中","general_chat；无数据工具调用",1,3,"gap",detail="模型仍有紧凑本人上下文和历史，但没有万能检索、任意 SQL、多工具规划或全量题库检索。"),
],[e("t0","t1","优先级1"),e("t0","t2","优先级2"),e("t0","t3","优先级3"),e("t1","t4","未命中继续"),e("t2","t5","未命中继续"),e("t3","t6","未命中继续"),e("t4","t7","仍无匹配"),e("t5","t7","仍无匹配"),e("t6","t7","仍无匹配")],refs=[src("router","IntentRouter"),src("agent","_tool_args")],note="图中六个候选并列用于展示映射；实际按 1→2→3→4→5→6 的字典顺序取首个，不并行执行。")
table(s,"Tool 输入、事实、计算与边界",["工具 / 示例提问","输入与选取规则","模型获得的实际数据","失败或实现边界"],[
["get_exam_summary\n这次考试总分多少？","exam_id 可选；未选时按总分记录 created_at 最新","exam_name/date、total_score、full_score、class/grade_rank、两级人数","无考试/分数返回错误；当前空满分回退150，与上下文空值策略不一致"],
["get_subject_scores\n数学多少分？","exam_id / subject_name；学科 ilike 模糊匹配；未选考试依据最新创建总分记录","subject_name、score/full_score、score_rate、两级排名/平均分、与均分差值","得分率=score/full_score×100；均分为0时真值判断会转成空值"],
["get_rank_change\n排名比上次怎样？","current_exam_id / previous_exam_id；所选考试比较日期更早的前次；可筛 subject_name","总分变化、班/年级名次变化；同科成绩/排名差","分差=当前-之前；名次改善=之前名次-当前名次。当前不校验两次满分和样本人群可比性"],
["get_score_trend\n数学成绩趋势？","exam_id 截止；subject_name 可选；limit默认5，限制1–20；主链路不从文本传limit","total_trend 或 subject_trend；考试ID/名称/日期、分数/满分、两级名次","需要总分记录作为考试集合；选学科时返回科目分支，不返回全科总分"],
["get_question_losses\n哪些题丢分最多？","exam_id / subject_name；min_loss默认0；limit默认10，限制1–20","question_no、subject_name、score/full_score/lost_score、loss_rate、answer_status、total_lost_score","total_lost_score仅所返回TOP N之和；min_loss=0可含零丢分题；不返回原题正文/答案/知识点诊断"],
["get_diagnosis\n有哪些学习建议？","实时查权益；exam_id可选；按generated_at取最新获授权正式报告","report_id/version、exam_id/name、report_type/status、structured、generated_at","不读取PDF/raw_content；当前忽略subject_name且未限定report_type=diagnosis"],
])
table(s,"来源名称 → 问答问题 → 引用类型",["数据名称","能回答的部分","sources.type","来源生产模块"],[
["total_score / class_rank / grade_rank","总分和排名事实","student_exam_score","成绩导入 → student_exam_scores"],
["score / full_score / class_avg / grade_avg","学科表现及均分对比","student_subject_score","成绩导入 → student_subject_scores"],
["question_no / lost_score / answer_status","小题丢分排序","question_score","成绩导入 → question_scores"],
["structured_json.summary / version / generated_at","已授权正式报告解读","diagnosis_report","正式报告原件 / 受控快照 → diagnosis_reports"],
["question_version.stem / answer / explanation","当前用于原题复盘页","未被六工具直接作为正文引用","试卷与题库补充流程"],
["knowledge_documents.content / reviews.correction","当前未作为问答检索或记忆","当前未接入","文档治理 / 学生复习"],
])
