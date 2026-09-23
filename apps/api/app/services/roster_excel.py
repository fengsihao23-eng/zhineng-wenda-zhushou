"""Fixed column contracts transcribed from 0922业务流程图_教师批量导入（新增）_V1.html."""
import base64
import io
import re
import zipfile
import xlrd
from openpyxl import Workbook, load_workbook
from app.core.errors import ApiError

TEACHER_COLUMNS = ["学校编号", "学校名称", "部门名称", "教师姓名", "性别", "教师账号", "学工号", "mac地址", "SN码", "状态", "说明", "身份证", "手机号码", "短号", "座机号", "电子邮箱", "备注", "任课年级班级", "班主任年级班级", "教研组长负责年级科目", "年级长负责年级", "是否教务主任", "是否校长", "是否总务主任"]
STUDENT_COLUMNS = ["学校编号", "学校名称", "年级（1-12）", "班级号", "姓名", "账号", "学号", "班级座号", "性别", "科类", "类别", "中/高考号", "学籍号", "全国学籍号", "准考证号", "身份证", "手机号", "email", "应往届", "状态", "考场号", "考场座位号", "mac地址 ", "SN码 ", "住宿类型", "宿舍类型", "宿舍楼", "楼层", "宿舍号", "床号"]
ERROR_COLUMNS = ["行号", "错误类型", "错误字段", "教师姓名", "教师账号", "错误说明", "原始内容", "处理建议"]
STUDENT_ERROR_COLUMNS = ["行号", "错误类型", "错误字段", "姓名", "账号", "错误说明", "原始内容", "处理建议"]
COLUMNS = {"teachers": TEACHER_COLUMNS, "students": STUDENT_COLUMNS}
GRADE_NAMES = {i: f"小学{n}年级" for i, n in enumerate("一二三四五六", 1)} | {7: "初中一年级", 8: "初中二年级", 9: "初中三年级", 10: "高中一年级", 11: "高中二年级", 12: "高中三年级"}

# The student flowchart embeds one redacted row as the current upload baseline.
STUDENT_TEMPLATE_ROWS = [[
    "441701004001", "阳江一中", "高中一年级", "1班", "张XX", "YJYZG20250110", "", "",
    "未知", "无", "正式生", "20250150", "20250110", "", "20250150", "", "", "", "应届", "正常",
    "1", "50", "", "", "默认", "", "", "", "", "",
]]
STUDENT_ERROR_TEMPLATE_ROWS = [
    ["行3", "必填缺失", "姓名", "（空）", "YJYZG20259999", "必填项「姓名」为空", "（空）", "补填姓名后整表重新上传"],
    ["行4", "必填缺失", "账号", "李四", "（空）", "必填项「账号」为空", "（空）", "补填账号后整表重新上传"],
    ["行5", "账号重复", "账号", "王五", "YJYZG20250002", "与系统已有学生账号重复（库内已存在，账号即登录账号）", "YJYZG20250002", "核实是否重复导入；如需修改该学生信息请走「变更（删旧 → 重导）」流程"],
    ["行6", "账号重复", "账号", "张六", "YJYZG20250003", "与本次文件内第 5 行的账号重复", "YJYZG20250003", "同一账号只能对应一名学生：保留一行，删除或更换另一行的账号"],
    ["行7", "必填缺失", "姓名、账号", "（空）", "（空）", "同一行存在多个错误：姓名与账号均为空", "（空）", "逐项补填后整表重新上传（同行多个错误合并为一条，错误字段列全部列出）"],
    ["行8", "状态非法", "状态", "赵七", "YJYZG20250004", "「状态」列取值非法（仅允许「正常」）", "休学", "状态改回「正常」后整表重新上传；休学 / 退学 / 毕业停用不通过导入办理，请到学生列表页用操作按钮处理"],
    ["文件", "列结构不符", "—", "—", "—", "列名或列顺序与《学生资料模板.xlsx》不一致（文件级错误，不做行级校验）", "缺列：全国学籍号", "对照现行模板修正表头后整份重新上传"],
]


def workbook_bytes(headers, rows=()):
    book = Workbook()
    sheet = book.active
    sheet.title = "资料"
    for values in [headers, *rows]:
        sheet.append([str(v) if v is not None else "" for v in values])
        # Values from uploads are text, including anything beginning with '='.
        for cell in sheet[sheet.max_row]:
            cell.data_type = "s"
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cells in sheet.columns:
        sheet.column_dimensions[cells[0].column_letter].width = min(48, max(18, len(str(cells[0].value)) * 2 + 2))
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def student_template_bytes():
    return workbook_bytes(STUDENT_COLUMNS, STUDENT_TEMPLATE_ROWS)


def student_error_template_bytes():
    return workbook_bytes(STUDENT_ERROR_COLUMNS, STUDENT_ERROR_TEMPLATE_ROWS)


def error_row(row, types, fields, messages, advice, kind):
    name, account = ("教师姓名", "教师账号") if kind == "teachers" else ("姓名", "账号")
    values = row.get("values", {})
    return {
        "row_number": row.get("row_number"),
        "error_type": "、".join(dict.fromkeys(types)),
        "fields": "、".join(dict.fromkeys(fields)),
        "name": values.get(name) or "（空）",
        "account": values.get(account) or "（空）",
        "message": "；".join(messages),
        "original": "；".join(f"{f}：{values.get(f) or '（空）'}" for f in dict.fromkeys(fields)),
        "suggestion": "；".join(dict.fromkeys(advice)),
    }


def file_issue(message, original=""):
    return {"row_number": None, "error_type": "列结构不符", "fields": "—", "name": "—", "account": "—", "message": message, "original": original, "suggestion": "对照现行模板修正后整份重新上传"}


def parse_excel(kind, filename, encoded):
    legacy_student = kind == "students" and filename.lower().endswith(".xls")
    if not filename.lower().endswith(".xlsx") and not legacy_student:
        raise ApiError(422, "XLSX_REQUIRED", "请上传现行模板的 Excel 文件（学生支持 .xls / .xlsx，教师支持 .xlsx）。")
    try:
        content = base64.b64decode(encoded, validate=True)
        if len(content) > 5_000_000:
            raise ApiError(413, "ROSTER_TOO_LARGE", "Excel 最大 5 MB、5000 行，请拆分文件。")
        if legacy_student:
            book = xlrd.open_workbook(file_contents=content, on_demand=True)
            try:
                sheet = book.sheet_by_index(0)
                if sheet.nrows > 5001 or sheet.ncols > 100:
                    raise ApiError(413, "ROSTER_TOO_LARGE", "Excel 最大 5000 行，请按固定模板上传。")
                return validate_rows(kind, (sheet.row_values(i) for i in range(sheet.nrows)))
            finally:
                book.release_resources()
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 40_000_000:
                raise ApiError(413, "ROSTER_TOO_LARGE", "Excel 解压后超过大小限制。")
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
        try:
            sheet = book.worksheets[0]
            if sheet.max_row > 5001 or sheet.max_column > 100:
                raise ApiError(413, "ROSTER_TOO_LARGE", "Excel 最大 5000 行，请按固定模板上传。")
            return validate_rows(kind, sheet.iter_rows(values_only=True))
        finally:
            book.close()
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(422, "EXCEL_INVALID", "Excel 无法读取，请核对文件格式或重新保存为 .xlsx 文件。") from exc


def validate_rows(kind, source):
    source = iter(source)
    columns = [text(value) for value in next(source, ())]
    expected = COLUMNS[kind]
    # The original student workbook has trailing spaces in mac/SN headers.
    compare = (lambda cs: [c.strip() for c in cs]) if kind == "students" else (lambda cs: cs)
    if compare(columns) != compare(expected):
        message = "列名或列顺序与《学生资料模板.xlsx》不一致（文件级错误，不做行级校验）" if kind == "students" else "列名或列顺序与资料模板不一致（文件级错误，不做行级校验）"
        return [], [file_issue(message, "、".join(columns))]
    rows = []
    for number, cells in enumerate(source, 2):
        values = [text(value) for value in cells]
        if not any(v.strip() for v in values):
            continue
        if number > 5001:
            raise ApiError(413, "ROSTER_TOO_LARGE", "Excel 最大 5000 行，请拆分文件。")
        if any(len(v) > 5000 for v in values):
            raise ApiError(422, "CELL_TOO_LONG", "单元格超过 5000 字，请核对文件。")
        rows.append({"row_number": number, "values": dict(zip(expected, values))})
    return rows, [] if rows else [file_issue("文件没有数据行，请填写资料后重新上传。")]


def text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def teaching_pairs(value):
    """Return subject, numeric grade, class. Unresolved references never reject teachers."""
    pairs = []
    for group in value.split(";"):
        if ":" not in group:
            continue
        subject, classes = group.split(":", 1)
        for code in classes.split(","):
            match = re.fullmatch(r"\s*(\d+)\.(\d+)\s*", code)
            if subject.strip() and match:
                pairs.append((subject.strip(), int(match[1]), int(match[2])))
    return pairs


def subject_leadership(value):
    """The real workbook can contain 10.语文,10.英语 in one leadership cell."""
    result = set()
    for item in re.split(r"[,，;；\n]", value):
        match = re.fullmatch(r"\s*(\d+)\.([^.,，;；\n]+?)\s*", item)
        if match:
            result.add((int(match[1]), match[2].strip()))
    return result


def class_matches(classroom, grade, number):
    return classroom.external_class_id == f"{grade}.{number}" or classroom.name.replace(" ", "") == f"{GRADE_NAMES.get(grade, grade)}{number}班"


def duty_codes(values):
    description = values.get("说明", "")
    def has_title(title):
        return bool(re.search(r"(?:^|[\n;,；，])\s*" + re.escape(title) + r"(?=\s*(?:[（(\n;,；，]|$))", description))
    roles = {"TEACHER"}
    if has_title("学校管理员"):
        roles.add("SCHOOL_ADMIN")
    if has_title("考试管理员"):
        roles.add("EXAM_ADMIN")
    for label, column, role in [
        ("班主任", "班主任年级班级", "HOMEROOM_TEACHER"),
        ("备课组长", "教研组长负责年级科目", "SUBJECT_LEADER"),
        ("年级长", "年级长负责年级", "GRADE_LEADER"),
    ]:
        if has_title(label) or (role == "SUBJECT_LEADER" and has_title("教研组长")) or values.get(column, "").strip():
            roles.add(role)
    for label, column, role in [("教务主任", "是否教务主任", "ACADEMIC_DIRECTOR"), ("校长", "是否校长", "PRINCIPAL"), ("总务主任", "是否总务主任", "GENERAL_DIRECTOR")]:
        if has_title(label) or values.get(column, "").strip().lower() in {"是", "1", "true", "yes"}:
            roles.add(role)
            roles.add("SCHOOL_VIEWER")
    return sorted(roles)
