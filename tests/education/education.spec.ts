import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
const fixture = JSON.parse(readFileSync(process.env.QA_FIXTURE_PATH!, "utf8"));
async function login(page: Page, role: string) {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(fixture.users[role]);
  await page.getByLabel("密码").fill(process.env.QA_PASSWORD!);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible();
}
async function logout(page: Page) {
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login$/);
}
function csvFiles(invalid = false) {
  const s = fixture.school_code;
  const rows: Record<string, string[][]> = {
    "schools.csv": [
      ["external_school_id", "name", "code"],
      ["qa-school", "QA 合成学校", s],
    ],
    "classes.csv": [
      ["external_class_id", "school_code", "name"],
      ["qa-import-class", s, "QA 导入班级"],
    ],
    "students.csv": [
      [
        "external_student_id",
        "school_code",
        "student_no",
        "name",
        "external_class_id",
      ],
      ["qa-import-student", s, "IMP001", "QA 导入学生", "qa-import-class"],
    ],
    "exams.csv": [
      ["external_exam_id", "school_code", "name", "exam_type", "start_date"],
      ["qa-import-exam", s, "QA 导入考试", "qa", "2026-09-18"],
    ],
    "subjects.csv": [
      ["external_subject_id", "school_code", "code", "name"],
      ["qa-math", s, "QA_MATH", "数学"],
    ],
    "student_exam_scores.csv": [
      [
        "external_student_id",
        "external_exam_id",
        "school_code",
        "total_score",
        "full_score",
      ],
      ["qa-import-student", "qa-import-exam", s, "88", "100"],
    ],
    "student_subject_scores.csv": [
      [
        "external_student_id",
        "external_exam_id",
        "external_subject_id",
        "school_code",
        "score",
        "full_score",
      ],
      ["qa-import-student", "qa-import-exam", "qa-math", s, "88", "100"],
    ],
    "question_scores.csv": [
      [
        "external_student_id",
        "external_exam_id",
        "external_subject_id",
        "school_code",
        "question_no",
        "score",
        "full_score",
        "lost_score",
      ],
      [
        "qa-import-student",
        "qa-import-exam",
        "qa-math",
        s,
        "1",
        invalid ? "9" : "2",
        "5",
        "3",
      ],
    ],
  };
  return Object.entries(rows).map(([name, lines]) => ({
    name,
    mimeType: "text/csv",
    buffer: Buffer.from(lines.map((r) => r.join(",")).join("\n")),
  }));
}

test("school workbench maintains class and teaching grant with persisted readback", async ({
  page,
}) => {
  await login(page, "admin");
  await page.goto("/admin/school");
  await page.getByRole("button", { name: "新建班级", exact: true }).click();
  await page.getByLabel("外部班级标识").fill("qa-native-class");
  await page.getByLabel("班级名称", { exact: true }).fill("QA 原生班级");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "QA 原生班级" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("row").filter({ hasText: "QA 原生班级" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "教师任教", exact: true }).click();
  await page.getByRole("button", { name: "新建教师任教", exact: true }).click();
  await page.getByLabel("教师账号").selectOption({ label: "QA teacher" });
  await page
    .getByLabel("班级", { exact: true })
    .selectOption({ label: "QA 原生班级" });
  await page
    .getByLabel("学科", { exact: true })
    .selectOption(fixture.subject_id);
  await page.getByLabel("生效时间").fill("2026-09-01T08:00");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "QA 原生班级" }),
  ).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("school-workbench-1280.png"),
    fullPage: true,
  });
});

test("CSV upload mapping preflight confirm receipt binding and real student readback", async ({
  page,
}) => {
  await login(page, "admin");
  await page.goto("/admin/imports");
  await page.getByLabel("批次编号").fill("browser-batch");
  await page.getByLabel("选择 CSV 文件").setInputFiles(csvFiles());
  await page.getByRole("button", { name: "上传新批次" }).click();
  await expect(page.getByRole("heading", { name: "批次详情" })).toBeVisible();
  await page.getByRole("button", { name: "保存映射并预检" }).click();
  await expect(page.getByText(/预检通过，共 8 行/)).toBeVisible();
  await page.getByLabel("已核对当前学校、映射和批次范围").check();
  await page.getByRole("button", { name: "确认导入", exact: true }).dblclick();
  await expect(page.getByRole("heading", { name: "导入回执" })).toBeVisible();
  await page.reload();
  await page
    .getByRole("row")
    .filter({ hasText: "browser-batch" })
    .getByRole("button")
    .click();
  await expect(page.getByRole("heading", { name: "导入回执" })).toBeVisible();
  await page.getByRole("link", { name: "进入学生账号绑定" }).click();
  await page.getByRole("button", { name: "学生与账号", exact: true }).click();
  await page
    .getByRole("row")
    .filter({ hasText: "QA 导入学生" })
    .getByRole("button", { name: "账号绑定", exact: true })
    .click();
  await page
    .getByLabel("账号", { exact: true })
    .selectOption({ label: "QA unbound" });
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "QA 导入学生" }),
  ).toContainText("已绑定账号");
  await logout(page);
  await login(page, "unbound");
  await page.goto("/profile");
  await expect(page.locator('.score-number')).toContainText('88');
  await expect(page.getByText('QA 导入考试', { exact: true }).first()).toBeVisible();
});

test("CSV invalid rows block confirmation and no-permission direct access is rejected", async ({
  page,
}) => {
  await login(page, "admin");
  await page.goto("/admin/imports");
  await page.getByLabel("批次编号").fill("browser-invalid");
  await page.getByLabel("选择 CSV 文件").setInputFiles(csvFiles(true));
  await page.getByRole("button", { name: "上传新批次" }).click();
  await page.getByRole("button", { name: "保存映射并预检" }).click();
  await expect(
    page.getByText("SCORE_EXCEEDS_FULL", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "确认导入", exact: true }),
  ).toHaveCount(0);
  await logout(page);
  await login(page, "student");
  await page.goto("/admin/imports");
  await expect(
    page.getByRole("heading", { name: "无权访问此页面" }),
  ).toBeVisible();
});

test("paper original upload split autosave refresh OCR and manual publish are real", async ({
  page,
}) => {
  await login(page, "admin");
  await page.goto("/admin/papers");
  await page
    .getByLabel("上传原件", { exact: true })
    .setInputFiles(fixture.pdf_path);
  await page.getByRole("button", { name: "校验并上传", exact: true }).click();
  await expect(page.getByText(/原件已保存：paper-two-pages.pdf/)).toBeVisible();
  await page.getByLabel("试卷名称").fill("QA 两页试卷");
  await page.getByLabel("考试", { exact: true }).selectOption(fixture.exam_id);
  await page
    .getByLabel("学科", { exact: true })
    .selectOption(fixture.subject_id);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await page.getByRole("link", { name: "拆题工作台" }).click();
  await expect(page.getByAltText("试卷原件第 1 页")).toBeVisible();
  const canvas = page.locator(".wb-canvas");
  const bounds = (await canvas.boundingBox())!;
  await page.mouse.move(
    bounds.x + bounds.width * 0.07,
    bounds.y + bounds.height * 0.04,
  );
  await page.mouse.down();
  await page.mouse.move(
    bounds.x + bounds.width * 0.95,
    bounds.y + bounds.height * 0.3,
  );
  await page.mouse.up();
  await page
    .getByLabel("题干", { exact: true })
    .fill("QA 人工确认题干：2 + 2 = ?");
  await page.getByLabel("参考答案", { exact: true }).fill("4");
  await page.getByLabel("解析", { exact: true }).fill("将两组各两个合并。");
  await expect(page.getByText(/草稿已保存 · 修订/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "立即保存草稿" }),
  ).toBeDisabled();
  await page.reload();
  await expect(page.getByLabel("题干", { exact: true })).toHaveValue(
    "QA 人工确认题干：2 + 2 = ?",
  );
  await page.getByLabel("继续框选当前题（跨页）").check();
  await page.getByLabel("页码", { exact: true }).selectOption("2");
  await expect(page.getByAltText("试卷原件第 2 页")).toBeVisible();
  await page.getByRole("button", { name: "新增可编辑区域" }).click();
  await expect(
    page.getByRole("button", { name: "立即保存草稿" }),
  ).toBeDisabled();
  await expect(page.getByText("2 个区域")).toBeVisible();
  await page.getByRole("button", { name: "发起 OCR / 失败重试" }).click();
  await expect(page.locator(".wb-badge--succeeded")).toBeVisible({
    timeout: 30000,
  });
  await expect(page.getByText(/Question/).first()).toBeVisible();
  await page.getByLabel("已逐题核对当前保存版本").check();
  await page.getByRole("button", { name: "人工确认并发布" }).dblclick();
  await expect(page.getByText(/已发布 1 道题/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/已发布 1 道题/)).toBeVisible();
  await expect(page.getByAltText('试卷原件第 1 页')).toBeVisible();
  await expect.poll(() => page.getByAltText('试卷原件第 1 页').evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  await page.screenshot({
    path: test.info().outputPath("split-workbench-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.app-sidebar')).toBeHidden();
  await expect(page.getByRole('button', {name:'切换导航'})).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByText("手机提供原件与草稿只读查看。")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "人工确认并发布" }),
  ).toBeHidden();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: test.info().outputPath("split-workbench-mobile.png"),
    fullPage: true,
    animations: 'disabled',
  });
});

test("taxonomy create tree reference protection and question source versions", async ({
  page,
}) => {
  await login(page, "admin");
  await page.goto("/admin/questions");
  await page
    .getByRole("button", { name: "知识点树与标签", exact: true })
    .click();
  await page.getByLabel("节点名称").fill("QA 加法知识点");
  await page
    .getByLabel("学科", { exact: true })
    .selectOption(fixture.subject_id);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(
    page.locator(".wb-tree").getByText("QA 加法知识点", { exact: false }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: "知识点树与标签", exact: true })
    .click();
  await expect(
    page.locator(".wb-tree").getByText("QA 加法知识点", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "题目与材料", exact: true }).click();
  await page.getByRole("button", { name: "新建题目", exact: true }).click();
  await page.getByLabel("题目名称").fill("QA 新建正式题");
  await page
    .getByLabel("学科", { exact: true })
    .selectOption(fixture.subject_id);
  await page.getByLabel("题干 / 材料正文").fill("计算 3 + 3。");
  await page.getByLabel("参考答案", { exact: true }).fill("6");
  await page.getByLabel("QA 加法知识点 · 知识点").check();
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await page.getByLabel("已核对最新题干、答案与标签").check();
  await page.getByRole("button", { name: "确认发布最新版本" }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "QA 新建正式题" }),
  ).toContainText("正式");
  await page
    .getByRole("button", { name: "知识点树与标签", exact: true })
    .click();
  await page
    .locator(".wb-tree li")
    .filter({ hasText: "QA 加法知识点" })
    .getByRole("button", { name: "软删除（检查引用）" })
    .click();
  await expect(page.getByText("记录仍被引用，不能删除。")).toBeVisible();
});

test("student original correction review is persistent and explicitly self-assessed", async ({
  page,
}) => {
  await login(page, "student");
  await page.goto("/mistakes");
  await page
    .getByRole("button", { name: "查看原题 / 加入复盘", exact: true })
    .click();
  await expect(
    page.getByText("合成题目：2 + 2 = ?", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "加入复盘（保存记录）" }).dblclick();
  await page
    .getByLabel("我的订正与复习笔记")
    .fill("QA 已重新计算，两组各两个合为四。");
  await page.getByLabel("自评掌握状态").selectOption("reviewing");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("复习记录已保存并重新读取。")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "查看 / 记录订正" }).click();
  await expect(
    page.getByText("QA 已重新计算，两组各两个合为四。", { exact: true }),
  ).toBeVisible();
});

test("human two-way messages return to the student after staff action", async ({
  page,
}) => {
  await login(page, "student");
  await page.goto("/support");
  await page.getByRole("button", { name: "联系老师" }).click();
  await expect(
    page.getByText("已提交人工转接，老师会在工作时间内联系你。"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "查看人工消息与处理进度" })
    .first()
    .click();
  await page.getByLabel("发送人工消息").fill("QA 双向消息问题");
  await page.getByRole("button", { name: "发送消息", exact: true }).click();
  await expect(
    page.getByText("QA 双向消息问题", { exact: true }),
  ).toBeVisible();
  await logout(page);
  await login(page, "admin");
  await page.goto("/admin/handoffs");
  const card = page.locator(".handoff-card").first();
  await card.getByRole("button", { name: "接单", exact: true }).click();
  await card.getByRole("button", { name: "查看人工消息与处理进度" }).click();
  await expect(
    card.getByText("QA 双向消息问题", { exact: true }),
  ).toBeVisible();
  await card.getByLabel("发送人工消息").fill("QA 老师回复：已核对原件。");
  await card.getByRole("button", { name: "发送消息", exact: true }).click();
  await logout(page);
  await login(page, "student");
  await page.goto("/support");
  await page
    .getByRole("button", { name: "查看人工消息与处理进度" })
    .first()
    .click();
  await expect(
    page.getByText("QA 老师回复：已核对原件。", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: "查看人工消息与处理进度" })
    .first()
    .click();
  await expect(
    page.getByText("QA 老师回复：已核对原件。", { exact: true }),
  ).toBeVisible();
});

test("chat selected context evidence and message feedback survive refresh", async ({
  page,
}) => {
  await login(page, "student");
  await page.goto("/chat");
  await page.getByLabel("问答考试范围").selectOption(fixture.exam_id);
  await expect(page.getByLabel("问答考试范围")).toHaveValue(fixture.exam_id);
  await page.getByLabel("问答学科范围").selectOption(fixture.subject_id);
  await expect(page.getByLabel("问答学科范围")).toHaveValue(fixture.subject_id);
  await page.getByRole("textbox", { name: "提问内容" }).fill("数学多少分");
  await page.getByRole("textbox", { name: "提问内容" }).press("Enter");
  await expect(
    page.getByRole("button", { name: "数学成绩 · 查看依据" }).last(),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "数学成绩 · 查看依据" })
    .last()
    .click();
  await expect(page.getByText("70", { exact: true }).last()).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: "数学成绩 · 查看依据" })
    .last()
    .click();
  await expect(page.getByText("70", { exact: true }).last()).toBeVisible();
  await page
    .getByRole("button", { name: "有帮助", exact: true })
    .last()
    .click();
  await expect(page.getByText("反馈已保存。").last()).toBeVisible();
});

test("new pages load errors retry and mobile navigation preserves charts", async ({
  page,
}) => {
  await login(page, "admin");
  let fail = true;
  await page.route("**/platform/education/questions?**", (route) =>
    fail
      ? route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ error: { message: "QA 题库暂时不可用" } }),
        })
      : route.continue(),
  );
  await page.goto("/admin/questions");
  await expect(page.getByText("QA 题库暂时不可用")).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "QA 复习原题" }),
  ).toBeVisible();
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    if (width <= 850) {
      await page.getByRole("button", { name: "切换导航" }).click();
      await expect(
        page.locator(".app-sidebar").getByRole("link", { name: "成绩导入" }),
      ).toBeVisible();
      await page.getByRole("button", { name: "关闭导航", exact: true }).click();
    }
  }
});
