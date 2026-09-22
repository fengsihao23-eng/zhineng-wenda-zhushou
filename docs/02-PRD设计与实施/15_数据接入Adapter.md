# PRD-15: 数据接入 Adapter 设计

---
Status: draft
Type: DESIGN-REFERENCE
Owner: 数据平台
Last verified: 2026-09-11
Evidence: 数据接入设计参考；CSV/Excel staging、幂等和失败隔离以导入测试为准。
Supersedes: 旧版 Adapter 示例
---

> 本文保留 Adapter 接口思路；第一阶段以 CSV/Excel 导入为主，不能把协议示例视为已实现。

## 1. 概述

Adapter 模式用于适配不同数据源，支持从旧系统、外部系统、新系统读取数据。

### 1.1 为什么需要 Adapter

**问题**：
- 旧系统使用 MySQL，新系统使用 PostgreSQL
- 可能有多个外部数据源（学校信息系统、考务系统）
- 数据格式不统一
- 需要渐进迁移

**解决**：
- 定义统一的数据接口
- 不同数据源实现各自的 Adapter
- 业务代码只依赖接口，不依赖具体实现

---

## 2. Adapter 接口设计

### 2.1 StudentDataAdapter

```python
from abc import ABC, abstractmethod
from typing import Protocol

class StudentDataAdapter(Protocol):
    """学生数据适配器接口"""
    
    async def get_student(self, student_id: UUID) -> Student:
        """获取学生信息"""
        ...
    
    async def list_exams(
        self,
        student_id: UUID,
        limit: int = 10
    ) -> list[Exam]:
        """获取学生的考试列表"""
        ...
    
    async def get_exam_score(
        self,
        student_id: UUID,
        exam_id: UUID
    ) -> ExamScore | None:
        """获取考试总分"""
        ...
    
    async def get_subject_scores(
        self,
        student_id: UUID,
        exam_id: UUID,
        subject: str | None = None
    ) -> list[SubjectScore]:
        """获取科目成绩"""
        ...
    
    async def get_question_scores(
        self,
        student_id: UUID,
        exam_id: UUID,
        subject: str | None = None
    ) -> list[QuestionScore]:
        """获取小题得分"""
        ...
```

---

## 3. PostgreSQL Adapter

### 3.1 实现

```python
class PostgresStudentDataAdapter(StudentDataAdapter):
    """PostgreSQL 原生 Adapter"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_student(self, student_id: UUID) -> Student:
        """从 PostgreSQL 读取学生"""
        result = await self.db.execute(
            select(StudentModel).where(StudentModel.id == student_id)
        )
        model = result.scalar_one_or_none()
        
        if not model:
            raise StudentNotFoundError(f"Student {student_id} not found")
        
        return Student.model_validate(model)
    
    async def list_exams(
        self,
        student_id: UUID,
        limit: int = 10
    ) -> list[Exam]:
        """获取学生参与的考试"""
        result = await self.db.execute(
            select(ExamModel)
            .join(StudentExamScore, StudentExamScore.exam_id == ExamModel.id)
            .where(StudentExamScore.student_id == student_id)
            .order_by(ExamModel.start_date.desc())
            .limit(limit)
        )
        
        return [Exam.model_validate(row) for row in result.scalars()]
    
    async def get_exam_score(
        self,
        student_id: UUID,
        exam_id: UUID
    ) -> ExamScore | None:
        """获取考试总分"""
        result = await self.db.execute(
            select(StudentExamScoreModel)
            .where(
                StudentExamScoreModel.student_id == student_id,
                StudentExamScoreModel.exam_id == exam_id
            )
        )
        
        model = result.scalar_one_or_none()
        return ExamScore.model_validate(model) if model else None
```

---

## 4. MySQL Legacy Adapter

### 4.1 实现

```python
class MySQLLegacyAdapter(StudentDataAdapter):
    """旧 MySQL 系统 Adapter"""
    
    def __init__(self, legacy_engine: Engine):
        self.engine = legacy_engine
    
    async def get_student(self, student_id: UUID) -> Student:
        """从旧 MySQL 读取学生"""
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT 
                        id,
                        student_name,
                        student_no,
                        grade_name,
                        class_name
                    FROM old_students
                    WHERE id = :student_id
                """),
                {"student_id": str(student_id)}
            )
            
            row = result.fetchone()
            if not row:
                raise StudentNotFoundError()
            
            # 映射到新模型
            return Student(
                id=uuid4(),  # 新生成
                external_student_id=row.id,
                name=row.student_name,
                student_no=row.student_no,
                grade=row.grade_name,
                class_name=row.class_name,
                source_system="legacy_mysql"
            )
    
    async def get_exam_score(
        self,
        student_id: UUID,
        exam_id: UUID
    ) -> ExamScore | None:
        """从旧系统读取成绩"""
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT 
                        s.id,
                        s.total_score,
                        s.rank as grade_rank,
                        s.class_rank,
                        e.total_students as grade_student_count
                    FROM old_exam_scores s
                    JOIN old_exams e ON s.exam_id = e.id
                    WHERE s.student_id = :student_id
                      AND s.exam_id = :exam_id
                """),
                {
                    "student_id": str(student_id),
                    "exam_id": str(exam_id)
                }
            )
            
            row = result.fetchone()
            if not row:
                return None
            
            return ExamScore(
                id=uuid4(),
                student_id=student_id,
                exam_id=exam_id,
                total_score=Decimal(str(row.total_score)),
                grade_rank=row.grade_rank,
                class_rank=row.class_rank,
                grade_student_count=row.grade_student_count,
                source_system="legacy_mysql"
            )
```

---

## 5. Adapter 配置与切换

### 5.1 配置

```python
# config.py
class AdapterConfig(BaseSettings):
    # 主数据源
    PRIMARY_ADAPTER: str = "postgres"  # 'postgres' or 'legacy_mysql'
    
    # 旧系统连接
    LEGACY_MYSQL_URL: str = "mysql://..."
    
    # 新系统连接
    POSTGRES_URL: str = "postgresql+asyncpg://..."
```

### 5.2 Factory 模式

```python
class AdapterFactory:
    """Adapter 工厂"""
    
    def __init__(
        self,
        postgres_db: AsyncSession,
        legacy_engine: Engine | None = None
    ):
        self.postgres_db = postgres_db
        self.legacy_engine = legacy_engine
    
    def create_adapter(
        self,
        adapter_type: str
    ) -> StudentDataAdapter:
        """创建 Adapter"""
        
        if adapter_type == "postgres":
            return PostgresStudentDataAdapter(self.postgres_db)
        
        elif adapter_type == "legacy_mysql":
            if not self.legacy_engine:
                raise ValueError("Legacy engine not configured")
            return MySQLLegacyAdapter(self.legacy_engine)
        
        else:
            raise ValueError(f"Unknown adapter type: {adapter_type}")
```

### 5.3 依赖注入

```python
# FastAPI 依赖
async def get_student_adapter(
    config: AdapterConfig = Depends(get_config),
    postgres_db: AsyncSession = Depends(get_db),
    legacy_engine: Engine | None = Depends(get_legacy_engine)
) -> StudentDataAdapter:
    """获取学生数据 Adapter"""
    
    factory = AdapterFactory(postgres_db, legacy_engine)
    return factory.create_adapter(config.PRIMARY_ADAPTER)
```

---

## 6. 外部系统同步

### 6.1 同步 Job

```python
class StudentDataSyncJob:
    """学生数据同步任务"""
    
    async def sync_from_legacy(self):
        """从旧系统同步数据"""
        
        legacy_adapter = MySQLLegacyAdapter(self.legacy_engine)
        postgres_repo = StudentRepository(self.postgres_db)
        
        # 获取旧系统最近更新的学生
        students = await legacy_adapter.list_updated_students(
            since=self.last_sync_time
        )
        
        for legacy_student in students:
            try:
                # 检查是否已存在
                existing = await postgres_repo.get_by_external_id(
                    external_student_id=legacy_student.id,
                    source_system="legacy_mysql"
                )
                
                if existing:
                    # 更新
                    await postgres_repo.update(
                        existing.id,
                        name=legacy_student.name,
                        student_no=legacy_student.student_no,
                        source_updated_at=legacy_student.updated_at
                    )
                else:
                    # 创建
                    await postgres_repo.create(
                        external_student_id=legacy_student.id,
                        name=legacy_student.name,
                        student_no=legacy_student.student_no,
                        source_system="legacy_mysql",
                        source_updated_at=legacy_student.updated_at
                    )
                
                logger.info(f"Synced student {legacy_student.id}")
                
            except Exception as e:
                logger.error(f"Failed to sync student {legacy_student.id}: {e}")
                continue
```

---

## 7. 幂等性保证

### 7.1 外部 ID + 哈希

```python
class SyncRecord(BaseModel):
    """同步记录"""
    external_id: str
    source_system: str
    data_hash: str          # 数据指纹
    last_sync_at: datetime

async def sync_with_idempotency(
    external_record: dict
) -> bool:
    """幂等同步"""
    
    # 计算数据哈希
    data_hash = hashlib.md5(
        json.dumps(external_record, sort_keys=True).encode()
    ).hexdigest()
    
    # 查询同步记录
    sync_record = await sync_record_repo.get_by_external_id(
        external_id=external_record["id"],
        source_system="legacy_mysql"
    )
    
    # 数据未变化，跳过
    if sync_record and sync_record.data_hash == data_hash:
        logger.info(f"Record {external_record['id']} unchanged, skip")
        return False
    
    # 同步数据
    await student_repo.upsert(external_record)
    
    # 更新同步记录
    await sync_record_repo.upsert(
        external_id=external_record["id"],
        source_system="legacy_mysql",
        data_hash=data_hash,
        last_sync_at=datetime.utcnow()
    )
    
    return True
```

---

## 8. 字段映射

### 8.1 映射配置

```yaml
# field_mapping.yaml
student:
  legacy_mysql:
    id: external_student_id
    student_name: name
    student_no: student_no
    grade_name: grade
    class_name: class_name
    
exam:
  legacy_mysql:
    exam_id: external_exam_id
    exam_name: name
    exam_type_code: exam_type
    exam_date: start_date
    
score:
  legacy_mysql:
    total_score: total_score
    rank: grade_rank
    class_rank: class_rank
```

### 8.2 映射器

```python
class FieldMapper:
    """字段映射器"""
    
    def __init__(self, mapping_config: dict):
        self.config = mapping_config
    
    def map_record(
        self,
        entity_type: str,
        source_system: str,
        source_record: dict
    ) -> dict:
        """映射记录"""
        
        mapping = self.config.get(entity_type, {}).get(source_system, {})
        
        result = {}
        for source_field, target_field in mapping.items():
            if source_field in source_record:
                result[target_field] = source_record[source_field]
        
        return result
```

---

## 9. 监控与告警

### 9.1 同步监控

```python
class SyncMonitor:
    """同步监控"""
    
    async def check_sync_health(self) -> SyncHealthReport:
        """检查同步健康度"""
        
        # 查询最近同步记录
        recent_syncs = await sync_log_repo.list_recent(hours=1)
        
        # 统计
        total = len(recent_syncs)
        success = sum(1 for s in recent_syncs if s.status == "success")
        failed = sum(1 for s in recent_syncs if s.status == "failed")
        
        # 检查延迟
        last_sync = await sync_log_repo.get_latest()
        delay_minutes = (datetime.utcnow() - last_sync.created_at).total_seconds() / 60
        
        return SyncHealthReport(
            total_syncs=total,
            success_rate=success / total if total > 0 else 0,
            failed_count=failed,
            delay_minutes=delay_minutes,
            is_healthy=success_rate > 0.95 and delay_minutes < 10
        )
```

### 9.2 告警

```python
async def alert_sync_failure(error: Exception, entity: str):
    """同步失败告警"""
    
    # 记录到日志
    logger.error(f"Sync failed for {entity}: {error}")
    
    # 发送告警（钉钉/企业微信/邮件）
    await alert_service.send(
        title="数据同步失败",
        content=f"实体: {entity}\n错误: {str(error)}",
        level="error"
    )
```

---

## 10. 测试

### 10.1 Adapter 测试

```python
async def test_postgres_adapter():
    """测试 PostgreSQL Adapter"""
    
    adapter = PostgresStudentDataAdapter(db)
    
    # 测试获取学生
    student = await adapter.get_student(test_student_id)
    assert student.name == "张三"
    
    # 测试获取考试
    exams = await adapter.list_exams(test_student_id, limit=5)
    assert len(exams) > 0

async def test_legacy_adapter():
    """测试 Legacy Adapter"""
    
    adapter = MySQLLegacyAdapter(legacy_engine)
    
    # 测试数据映射
    student = await adapter.get_student(legacy_student_id)
    assert student.source_system == "legacy_mysql"
    assert student.external_student_id is not None
```

### 10.2 同步测试

```python
async def test_sync_idempotency():
    """测试同步幂等性"""
    
    # 第一次同步
    result1 = await sync_job.sync_student(legacy_student_id)
    assert result1 == True
    
    # 第二次同步（数据未变）
    result2 = await sync_job.sync_student(legacy_student_id)
    assert result2 == False  # 跳过
```

---

## 11. 关键要点

1. **定义统一的 Adapter 接口**
2. **不同数据源各自实现 Adapter**
3. **业务代码只依赖接口**
4. **支持配置化切换数据源**
5. **同步要保证幂等性**
6. **字段映射配置化**
7. **监控同步健康度**
