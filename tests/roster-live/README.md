# 真实教师资料与 DeepSeek Flash 联调

此目录为显式运行的本地联调，使用用户提供的真实 Excel 和配置的真实模型 API。普通 CI 不自动运行此套测试。

运行环境为 `scripts/roster_preview.mjs` 启动的独立应用，数据库固定为 `yjyz_roster_20260922`，与生产业务库和会被清空的 pytest 数据库隔离。真实学校使用原学校代码；破坏性测试在独立 `QA-YJYZ-*` 学校使用合成姓名和账号。

## 启动

```bash
# 在已配置隔离 QA PostgreSQL 的本机创建专用数据库，仅首次需要
# 已存在时不要重复创建或清空
docker exec qa-education-20260918 createdb -U qa_education yjyz_roster_20260922

# 安装 requirements.txt 后，在仓库根目录运行
node scripts/roster_preview.mjs
```

预览服务读取 Git 忽略的 `apps/api/.env` 中 DeepSeek 配置，不在源码保存密钥；自动执行数据库迁移并构建生产前端，默认只监听 `127.0.0.1:61564`。`ROSTER_PREVIEW_PORT` 可覆盖 Web 端口（测试配置须一致修改）。私密账号、入口和状态保存在 `.local/yjyz-roster/`，不得提交或公开。

## 联调

```bash
# 以下 DATABASE_URL 只允许指向本次专用库
export DATABASE_URL=postgresql+asyncpg://qa_education@127.0.0.1:55449/yjyz_roster_20260922
export APP_ENV=test
export DEBUG=false
export PYTHONPATH=apps/api

# 读取原始文件，建立文件实际引用的班级、学科字典，并准备独立测试学校
.venv/bin/python tests/roster-live/prepare.py

# 浏览器真实上传160名教师，核验账号/字段；副本执行改密、权限、生命周期与真实问答
node node_modules/@playwright/test/cli.js test --config tests/roster-live/playwright.config.ts

# 独立数据库回读，验证授权数、操作日志、真实模型调用记录及毕业后的历史保留
.venv/bin/python tests/roster-live/verify_database.py
```

重复执行时，已导入的 160 名教师只做回读和登录核验，不删除、不改密、不停用；`prepare.py` 会建立新的合成测试学校。测试第一次确认会导入真实学校；后续重复导入演练只预校验并验证拒绝写入。

已执行的 2026-09-22 验收分为 4 条主链路 + 1 条移交/调班补充链路。测试中的真实模型调用仅使用合成学生成绩与问题，不发送真实教师姓名、账号或手机号。结果 JSON、真实人员信息及运行状态仅写入 `.local`；对外验收文档只写汇总数据。
