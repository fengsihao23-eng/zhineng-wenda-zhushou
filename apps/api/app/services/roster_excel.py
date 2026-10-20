"""Fixed teacher/student roster contracts from the r79 flow and prototypes."""
import base64
import io
import re
import unicodedata
import zipfile
from itertools import zip_longest
import xlrd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Protection
from app.core.errors import ApiError

TEACHER_COLUMNS = ["学校编号", "学校名称", "部门名称", "教师姓名", "性别", "教师账号", "学工号", "mac地址", "SN码", "状态", "说明", "身份证", "手机号码", "短号", "座机号", "电子邮箱", "备注", "任课年级班级", "班主任年级班级", "教研组长负责年级科目", "年级长负责年级", "是否教务主任", "是否校长", "是否总务主任"]
STUDENT_COLUMNS = ["学校编号", "学校名称", "年级（1-12）", "班级号", "姓名", "账号", "学号", "班级座号", "性别", "科类", "类别", "中/高考号", "学籍号", "全国学籍号", "准考证号", "身份证", "手机号", "email", "应往届", "状态", "考场号", "考场座位号", "mac地址", "SN码", "住宿类型", "宿舍类型", "宿舍楼", "楼层", "宿舍号", "床号"]
# The original school .xls template has one trailing space in these two headers.
# Resolve only those historical names; retain strict names/order for other columns.
STUDENT_HEADER_ALIASES = {"mac地址 ": "mac地址", "SN码 ": "SN码"}
STUDENT_CHANGE_COLUMNS = STUDENT_COLUMNS + ["学生ID"]
STUDENT_LOCKED_FIELDS = ["学校编号", "学校名称", "姓名", "账号", "年级（1-12）", "班级号", "状态", "学生ID"]
STUDENT_PROMOTION_COLUMNS = ["学生ID", "账号", "姓名", "目标年级", "目标班级号"]
ERROR_COLUMNS = ["行号", "错误类型", "错误字段", "教师姓名", "教师账号", "错误说明", "原始内容", "处理建议"]
STUDENT_ERROR_COLUMNS = ["行号", "错误类型", "错误字段", "姓名", "账号", "错误说明", "原始内容", "处理建议"]
COLUMNS = {"teachers": TEACHER_COLUMNS, "students": STUDENT_COLUMNS}
TEACHER_CHANGE_COLUMNS = TEACHER_COLUMNS + ["教师ID"]
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
    ["行5", "账号重复", "账号", "王五", "YJYZG20250002", "与系统已有学生账号重复（库内已存在，账号即登录账号）", "YJYZG20250002", "修改错误账号后整表重传；本人资料修正请走「档案变更」或「姓名·账号变更」"],
    ["行6", "账号重复", "账号", "张六", "YJYZG20250003", "与本次文件内第 5 行的账号重复", "YJYZG20250003", "同一账号只能对应一名学生：保留一行，删除或更换另一行的账号"],
    ["行7", "必填缺失", "姓名、账号", "（空）", "（空）", "同一行存在多个错误：姓名与账号均为空", "（空）", "逐项补填后整表重新上传（同行多个错误合并为一条，错误字段列全部列出）"],
    ["行8", "状态非法", "状态", "赵七", "YJYZG20250004", "「状态」列取值非法（仅允许「正常」）", "离校", "状态改回「正常」后整表重新上传；离校 / 毕业 / 恢复在读请在学生列表办理"],
    ["文件", "列结构不符", "—", "—", "—", "列名或列顺序与《学生资料模板.xlsx》不一致（文件级错误，不做行级校验）", "缺列：全国学籍号", "对照现行模板修正表头后整份重新上传"],
]


def workbook_bytes(headers, rows=(), lock_teacher_id=False, locked_fields=()):
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
    if lock_teacher_id or locked_fields:
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.protection = Protection(locked=(cell.column == len(headers) if lock_teacher_id else headers[cell.column - 1] in locked_fields))
        sheet.protection.sheet = True
        sheet.protection.autoFilter = False
    for cells in sheet.columns:
        sheet.column_dimensions[cells[0].column_letter].width = min(48, max(18, len(str(cells[0].value)) * 2 + 2))
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def student_template_bytes():
    return workbook_bytes(STUDENT_COLUMNS, STUDENT_TEMPLATE_ROWS)


def teacher_template_bytes():
    """A fresh checkout has no private workbook; provide the same 24-column contract."""
    return workbook_bytes(TEACHER_COLUMNS)


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


def parse_excel(kind, filename, encoded, columns=None):
    legacy_excel = filename.lower().endswith(".xls")
    if not filename.lower().endswith(".xlsx") and not legacy_excel:
        raise ApiError(422, "XLSX_REQUIRED", "请上传现行模板的 Excel 文件（.xls / .xlsx）。")
    try:
        content = base64.b64decode(encoded, validate=True)
        if len(content) > 5_000_000:
            raise ApiError(413, "ROSTER_TOO_LARGE", "Excel 最大 5 MB、5000 行，请拆分文件。")
        if legacy_excel:
            book = xlrd.open_workbook(file_contents=content, on_demand=True)
            try:
                sheet = book.sheet_by_index(0)
                if sheet.nrows > 5001 or sheet.ncols > 100:
                    raise ApiError(413, "ROSTER_TOO_LARGE", "Excel 最大 5000 行，请按固定模板上传。")
                return validate_rows(kind, (sheet.row_values(i) for i in range(sheet.nrows)), columns)
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
            return validate_rows(kind, sheet.iter_rows(values_only=True), columns)
        finally:
            book.close()
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(422, "EXCEL_INVALID", "Excel 无法读取，请核对文件格式或重新保存为 .xlsx 文件。") from exc


def validate_rows(kind, source, expected_columns=None):
    source = iter(source)
    columns = [text(value) for value in next(source, ())]
    expected = expected_columns or COLUMNS[kind]
    resolved = [STUDENT_HEADER_ALIASES.get(column, column) for column in columns] if kind == "students" else columns
    if resolved != expected:
        message = "列名或列顺序与《学生资料模板.xlsx》不一致（文件级错误，不做行级校验）" if kind == "students" else "列名或列顺序与资料模板不一致（文件级错误，不做行级校验）"
        differences = []
        for number, (actual, required) in enumerate(zip_longest(resolved, expected), 1):
            if actual == required:
                continue
            if actual is None:
                differences.append(f"第 {number} 列缺少「{required}」")
            elif required is None:
                differences.append(f"第 {number} 列多出「{actual}」")
            else:
                differences.append(f"第 {number} 列应为「{required}」，实际为「{actual}」")
        detail = "；".join(differences[:8])
        if len(differences) > 8:
            detail += f"；另有 {len(differences) - 8} 处列结构错误"
        return [], [file_issue(f"{message}：{detail}", "、".join(columns))]
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
    subject = ""
    for group in re.split(r"[;\n\r]+", normalized(value)):
        if ":" in group:
            subject, classes = group.split(":", 1)
        else:
            classes = group
        for grade, number in class_references(classes):
            if subject.strip():
                pairs.append((subject.strip(), grade, number))
    return pairs


def subject_leadership(value):
    """The real workbook can contain 10.语文,10.英语 in one leadership cell."""
    result = set()
    for item in re.split(r"[,;\n\r、]", normalized(value)):
        match = re.fullmatch(r"\s*(\d+)\.([^.,，;；\n]+?)\s*", item)
        if match:
            result.add((int(match[1]), match[2].strip()))
    return result


def class_matches(classroom, grade, number):
    expected = parse_class_reference(f"{grade}.{number}") or parse_class_reference(f"{grade}{number}班")
    return bool(expected and expected in (parse_class_reference(classroom.external_class_id), parse_class_reference(classroom.name)))


def normalized(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def parse_class_reference(value):
    value = re.sub(r"\s+", "", normalized(value))
    match = re.fullmatch(r"(\d+)\.(\d+)", value)
    if match:
        return int(match[1]), int(match[2])
    for grade, label in GRADE_NAMES.items():
        match = re.fullmatch(re.escape(label) + r"(\d+)班", value)
        if match:
            return grade, int(match[1])
    return None


def class_references(value):
    return [reference for part in re.split(r"[,;、\n\r]+", normalized(value))
            if (reference := parse_class_reference(part))]


def grade_codes(value):
    labels = {label: grade for grade, label in GRADE_NAMES.items()}
    return {int(part) if part.isdigit() else labels[part]
            for part in re.split(r"[,;、\s]+", normalized(value)) if part.isdigit() or part in labels}


def duty_codes(values):
    roles = {"TEACHER"}
    for label, column, role in [
        ("班主任", "班主任年级班级", "HOMEROOM_TEACHER"),
        ("备课组长", "教研组长负责年级科目", "SUBJECT_LEADER"),
        ("年级长", "年级长负责年级", "GRADE_LEADER"),
    ]:
        if values.get(column, "").strip():
            roles.add(role)
    for label, column, role in [("教务主任", "是否教务主任", "ACADEMIC_DIRECTOR"), ("校长", "是否校长", "PRINCIPAL"), ("总务主任", "是否总务主任", "GENERAL_DIRECTOR")]:
        if values.get(column, "").strip().lower() in {"是", "1", "true", "yes"}:
            roles.add(role)
            roles.add("SCHOOL_VIEWER")
    return sorted(roles)
