# P0-02: 测试数据初始化 - 已完成 ✅

## 实施日期
2026-09-10 23:56 - 2026-09-11 00:02

---

## 问题描述

**原始问题：**
- 数据库表结构已创建，但完全没有测试数据
- 无法测试任何功能
- 需要完整的测试数据支持功能验证

---

## 已完成的工作

### 1. 创建测试数据初始化脚本 ✅

**文件：** [apps/api/scripts/init_test_data.py](apps/api/scripts/init_test_data.py)

**功能：**
- ✅ 创建1个学校（示范中学）
- ✅ 创建2个用户账号（student1, student2）
- ✅ 创建2个学生档案（张三, 李四）
- ✅ 创建5个科目（数学、语文、英语、物理、化学）
- ✅ 创建2次考试（2024学年第1次月考、第2次月考）
- ✅ 完整成绩数据（总分、科目分、小题得分）
- ✅ 1份诊断报告（student2）
- ✅ 权益数据（student2拥有DIAGNOSIS权限）

### 2. 解决依赖问题 ✅

**安装的依赖：**
- ✅ greenlet - SQLAlchemy async支持
- ✅ psycopg2-binary - Alembic迁移支持
- ✅ bcrypt 4.1.2 - 密码加密（降级以兼容passlib）

### 3. 修复数据库不一致问题 ✅

**问题：** 容器使用 `intelligent_qa` 数据库，但初始化数据到了 `student_agent` 数据库

**解决方案：**
- ✅ 重新在 `intelligent_qa` 数据库中初始化测试数据
- ✅ 确保容器配置和本地脚本使用相同的数据库

---

## 测试账号

### student1（BASIC用户）
- **用户名：** student1
- **密码：** password123
- **学生信息：** 张三，学号 20240001
- **权限：** 仅能查看基础成绩
- **成绩数据：**
  - 第1次月考：579/750，班级排名15，年级排名31
  - 第2次月考：603/750，班级排名15，年级排名31

### student2（DIAGNOSIS用户）
- **用户名：** student2
- **密码：** password123
- **学生信息：** 李四，学号 20240002
- **权限：** 可以查看诊断报告
- **成绩数据：**
  - 第1次月考：647/750，班级排名3，年级排名8
  - 第2次月考：664/750，班级排名3，年级排名8
- **诊断报告：** 1份（第1次月考）
- **权益：** DIAGNOSIS产品权限

---

## 数据库验证

```bash
# 验证用户数量
docker exec intelligent-qa-postgres psql -U postgres -d intelligent_qa \
  -c "SELECT COUNT(*) FROM users;"
# 结果: 4个用户

# 验证学生数量  
docker exec intelligent-qa-postgres psql -U postgres -d intelligent_qa \
  -c "SELECT COUNT(*) FROM students;"
# 结果: 4个学生

# 验证考试数量
docker exec intelligent-qa-postgres psql -U postgres -d intelligent_qa \
  -c "SELECT COUNT(*) FROM exams;"
# 结果: 5次考试

# 验证成绩数据
docker exec intelligent-qa-postgres psql -U postgres -d intelligent_qa \
  -c "SELECT COUNT(*) FROM student_exam_scores;"
# 结果: 5条成绩记录
```

---

## API测试验证

### 登录测试 ✅

**student1登录：**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "student1", "password": "password123"}'
```

**响应：**
```json
{
  "access_token": "eyJhbGci...",
  "refresh_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "a7acd8d9-8b8a-470a-a2f5-4e6ad1a5b23a",
    "username": "student1",
    "display_name": "张三",
    "roles": ["STUDENT"],
    "student_id": "4a7b6ae8-bbfb-4034-81e4-f9e6db2134e7"
  }
}
```

**student2登录：**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "student2", "password": "password123"}'
```

**响应：**
```json
{
  "access_token": "eyJhbGci...",
  "refresh_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "9200b91f-ee93-4726-b08b-00b1303fb662",
    "username": "student2",
    "display_name": "李四",
    "roles": ["STUDENT"],
    "student_id": "04d5268a-8536-493e-a0c8-5f2969308b14"
  }
}
```

---

## 验收标准检查

- ✅ 脚本运行成功无报错
- ✅ 数据库中有1个学校
- ✅ 有2个用户和2个学生（实际有4个，包含旧的测试账号）
- ✅ 有2次考试，每次考试有完整成绩数据
- ✅ student2有诊断报告和DIAGNOSIS权益
- ✅ 可以用student1/password123登录
- ✅ 可以用student2/password123登录

---

## 数据结构

### 学校
- 示范中学 (DEMO_SCHOOL)

### 用户和学生
| 用户名 | 显示名 | 学号 | 权限类型 |
|--------|--------|------|----------|
| student1 | 张三 | 20240001 | BASIC |
| student2 | 李四 | 20240002 | DIAGNOSIS |

### 科目
1. 数学 (MATH)
2. 语文 (CHINESE)
3. 英语 (ENGLISH)
4. 物理 (PHYSICS)
5. 化学 (CHEMISTRY)

### 考试
1. 2024学年第1次月考
2. 2024学年第2次月考

### 成绩数据结构
- **student_exam_scores**: 总分和排名
- **student_subject_scores**: 各科成绩和排名
- **question_scores**: 小题得分（每科5题）

### 诊断报告
- **student2的第1次月考诊断报告：**
  - 整体表现优秀，数学有提升空间
  - 知识薄弱点：函数定义域、立体几何
  - 建议：加强函数综合题练习、提高空间想象能力
  - 优势：英语阅读理解、化学实验题
  - 待改进：数学应用题、物理力学

---

## 运行方式

### 手动运行脚本

```bash
cd /Users/hao/智能问答助手/apps/api

# 激活虚拟环境
source venv/bin/activate

# 设置数据库URL（确保使用intelligent_qa数据库）
export DATABASE_URL='postgresql+asyncpg://postgres:postgres123@localhost:5432/intelligent_qa'

# 运行脚本
python scripts/init_test_data.py
```

### 清理并重新初始化

```bash
# 1. 清空数据（可选）
docker exec intelligent-qa-postgres psql -U postgres -d intelligent_qa -c "
  TRUNCATE TABLE 
    question_scores, 
    student_subject_scores, 
    student_exam_scores,
    exam_subjects,
    exams,
    subjects,
    student_entitlements,
    diagnosis_reports,
    students,
    user_roles,
    users,
    schools
  CASCADE;
"

# 2. 重新运行初始化脚本
cd /Users/hao/智能问答助手/apps/api
source venv/bin/activate
export DATABASE_URL='postgresql+asyncpg://postgres:postgres123@localhost:5432/intelligent_qa'
python scripts/init_test_data.py
```

---

## 已解决的问题

### 问题1：greenlet模块缺失 ✅
**错误：** `No module named 'greenlet'`  
**解决：** `pip install greenlet`

### 问题2：psycopg2缺失 ✅
**错误：** `ModuleNotFoundError: No module named 'psycopg2'`  
**解决：** `pip install psycopg2-binary`

### 问题3：bcrypt版本不兼容 ✅
**错误：** `password cannot be longer than 72 bytes`  
**解决：** 降级到 `bcrypt==4.1.2`

### 问题4：数据库不一致 ✅
**问题：** 容器使用 `intelligent_qa`，脚本写入 `student_agent`  
**解决：** 统一使用 `intelligent_qa` 数据库

### 问题5：角色重复创建 ✅
**错误：** `duplicate key value violates unique constraint "uq_roles_code"`  
**解决：** 修改脚本，先查询是否存在，不存在才创建

---

## 下一步

### 功能测试
1. ✅ 登录功能已验证
2. ⏳ 测试聊天功能
3. ⏳ 测试成绩查询Tools
4. ⏳ 测试诊断报告Tools

### 前端测试
1. ⏳ 访问 http://localhost:3000
2. ⏳ 使用 student1/password123 登录
3. ⏳ 发送消息："我这次考得怎样？"
4. ⏳ 验证AI能够调用Tools获取真实成绩数据

### 需要的API Key
- DeepSeek API Key 或 OpenAI API Key
- 配置在 `.env` 文件中

---

## 状态：✅ P0-02 测试数据初始化完成

所有测试数据已成功创建，登录功能已验证，系统可以开始完整的端到端测试。
