# 平台工作台与运行约定

## 页面与 API

学生登录后进入学习总览，可从侧边栏访问 `/trends`、`/diagnosis`、`/mistakes`、`/chat` 和 `/support`。这些页面分别调用 `/api/v1/platform/student/*`，成绩、诊断和错题均来自当前学生的数据范围。

教师、学校管理员和市级运营分别进入 `/teacher`、`/admin` 和 `/ops`。管理接口统一位于 `/api/v1/platform/management/*`，权限由用户角色和学校范围在服务端校验：教师只能处理本校教学事件，学校管理员管理本校治理流程，市级运营和超级管理员可以查看跨校聚合数据。

知识库状态流转为：`draft → pending_review → published → offline`。每个文档必须记录来源名称、来源链接或文件引用，发布和下线都需要留下审核人及时间。`POST /management/knowledge/{id}/review` 支持提交、通过、驳回、下线和重新发布动作。

学生可创建家长授权申请，家长使用一次性授权码调用 `/api/v1/platform/parent/authorizations/{id}/approve` 完成确认。反馈、风险事件和人工转接分别由学生提交、管理台分派/确认/解决，状态变化会写入对应工作流记录。

## 初始化与测试账号

数据库迁移会创建平台工作流表并补充 `CITY_OPERATOR` 角色。开发环境初始化：

```bash
export DATABASE_URL='postgresql+asyncpg://postgres:<password>@localhost:5432/intelligent_qa'
python3 scripts/setup_database.py
```

初始化脚本会幂等创建成绩、诊断、知识库、风险和人工转接示例，并创建这些密码均为 `password123` 的账号：

- `student_basic`：学生总览与基础成绩数据
- `student_diagnosis`：学生诊断报告数据
- `teacher_demo`：教师工作台
- `school_admin_demo`：学校管理台
- `city_operator_demo`：市级运营中心

## 模型运行模式

`MODEL_PROVIDER=auto` 是默认值。它只会选择配置了有效 API Key 的 OpenAI 或 DeepSeek Provider；没有真实凭据时，健康接口会返回 `real_model_ready=false`，聊天会返回明确的配置错误，绝不会静默使用确定性模型。`MODEL_PROVIDER=fake` 仅用于测试和契约测试。

例如使用 DeepSeek：

```dotenv
MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=真实密钥
DEFAULT_MODEL=deepseek-chat
```

访问 `/api/v1/health` 可以检查 Provider 状态，`/health` 是 nginx 的公开探针入口。
