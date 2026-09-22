# Bug 与成绩页面复查报告

> 修复跟踪：本报告保留 2026-09-16 的问题和原始证据。对应问题的修复、部署与新增验收结果见 [2026-09-17 修复验收记录](QA_FIX_2026-09-17.md)。

检查日期：2026-09-16。结论：**未全部完成，不能据现有“全部修复”报告通过验收。**

本次检查当前工作区（包含已有未提交修改）、现有运行容器、浏览器真实登录流程和隔离数据库测试。没有修改业务代码、重启部署或更改成绩数据。新增本报告及证据文件；前端构建重新生成了本地 dist。

## 逐项结论

| 验收项 | 结论 | 证据与限制 |
| --- | --- | --- |
| 统一 TanStack Query | 未完成 | 只有新 `/profile` 接入；旧学生页、管理页和聊天仍各自维护请求状态。已复现账号切换后缓存串号。 |
| 统一错误格式和 UI | 部分完成 | 业务 HTTP 异常和参数错误已规范；404/405仍是旧格式；多数页面未使用统一组件；断网仍显示英文 `Failed to fetch`。 |
| N+1 查询优化 | 主要列表在源码中完成，运行版未完成 | 隔离 SQL 计数：1/50 条记录时学生、学校列表均固定3次 SELECT；运行容器的学校列表仍在循环内查询。实现使用 JOIN、窗口函数和批量聚合，`joinedload` 仅导入，未实际使用。 |
| structlog 结构化日志 | 部分完成 | 标准输出有 JSON，但业务日志没有写入配置的日志文件；异常缺堆栈、请求上下文未绑定、日志级别不生效。运行容器仍无新版 structlog 配置。 |
| 学生成绩正常显示 | 常规数据可显示，完整验收不通过 | 独立登录李四664分、张三603分均显示正确；切换账号后概览串号；缺失满分会出现 `Infinity%`。部署版 `/profile` 为空白页。 |
| 图表渲染正确 | 不通过 | 雷达图被深灰实心轴线多边形遮挡；总分与百分比共用纵轴；概览全局样式把首页进度条从5px变为实测63px。 |
| 移动端适配 | 部分通过 | 稳定布局下375/390/768px主体无横向溢出；320px下内容区宽230px、滚动宽240px，仍溢出10px。 |
| 加载时间 <2s | 本机首次内容可见达标，完整性能验收未完成 | 当前生产构建本机5次禁用浏览器缓存导航，成绩首次可见159–186ms。未覆盖真实网络、手机设备与正式部署的新版本；现有自动化实际要求3s且不测 `/profile`。 |

## 优先问题与复现

### P1：切换账号显示上一位学生的成绩

浏览器在当前源码前端 `http://localhost:5173` 的同一个标签页中完成以下操作：

1. 登录测试账号 `student_diagnosis`，进入成绩概览，显示李四、664/750。
2. 点击退出登录，再登录测试账号 `student_basic`。首页正确显示张三、603/750。
3. 点击侧栏“成绩概览”：仍显示李四、664/750；从点击到页面出现，没有发出任何新的学生成绩请求。

这是实际可复现的账号间数据串用，不只是短暂加载占位。

根因：[useApi.ts:56](../../apps/web/src/hooks/useApi.ts:56) 查询键不含身份；[useApi.ts:93](../../apps/web/src/hooks/useApi.ts:93) 缓存5分钟；[AppShell.tsx:74](../../apps/web/src/layouts/AppShell.tsx:74) 退出只清认证信息，未取消旧请求或清 QueryClient 缓存。

修复方向：查询键包含账号/学生身份，身份变化时取消旧账号请求并清理缓存，增加同标签页切换账号回归测试。

证据：[账号切换截图](qa-recheck-2026-09-16/cross-account-cache.png)、[浏览器观测结果](qa-recheck-2026-09-16/browser-results.json)。

### 部署状态：运行版尚未包含修复

运行容器的 `errors.py`、`logging.py`、`main.py`、`platform.py` 与工作区校验值均不同。容器中没有新的 structlog 配置、user_message 或 row_number；学校列表仍存在每所学校两次查询，即1+2N。

真实登录 `http://localhost` 后，导航没有“成绩概览”；直接访问 `/profile`，页面正文为空、根节点仅剩空容器。HTTP 200 是单页应用回退响应，不能据此认定页面可用。

证据：[部署版空白页](qa-recheck-2026-09-16/deployed-profile.png)、[部署版检查结果](qa-recheck-2026-09-16/edge-results.json)。检查期间未重新部署。

### P2：雷达图数据被轴线填充遮住

稳定渲染后，雷达图显示深灰色规则五边形，遮住紫色数据区域及网格。页面 DOM 中 `.recharts-polar-angle-axis-line` 虽有 `fill="none"`，同时具有优先级更高的 `style="fill: rgb(55,65,81)"`。

根因：[Profile.tsx:177](../../apps/web/src/pages/Profile.tsx:177) 将刻度文字颜色设置在整个 `PolarAngleAxis` 的 style 上，被 Recharts 传给轴线多边形。应改为仅作用于 tick 的样式。

另外，[Profile.tsx:101](../../apps/web/src/pages/Profile.tsx:101) 只定义一条纵轴，让600多分与80多%的曲线共用分数刻度，得分率变化被压缩到图底；应使用独立百分比轴或统一指标。

证据：[图表稳定状态截图](qa-recheck-2026-09-16/charts-stable.png)、[包含 SVG DOM 的观测结果](qa-recheck-2026-09-16/stable-results.json)。

### P2：全局样式影响首页，窄屏尚有溢出

[Profile.css:332](../../apps/web/src/pages/Profile.css:332) 的全局 `.progress-bar { height:100% }` 覆盖 [AppShell.css:569](../../apps/web/src/layouts/AppShell.css:569) 原有5px高度。首页五个科目的轨道均实测63px，应将概览样式限定在其自身组件内。

移动端采用独立浏览器上下文，在初始视口375/390/320/768px下登录并等待布局及动画稳定。375/390/768px主体无横向溢出；320px存在10px溢出。未将窗口缩放动画进行中的瞬时布局作为失败证据。

证据：[375px截图](qa-recheck-2026-09-16/profile-stable-375.png)、[320px截图](qa-recheck-2026-09-16/profile-stable-320.png)。

### P2：缺失满分会显示 Infinity%

数据库允许总分满分为空，[platform.py:194](../../apps/api/app/api/v1/endpoints/platform.py:194) 会将其转成0；[Profile.tsx:26](../../apps/web/src/pages/Profile.tsx:26) 和第82行未检查分母。

使用浏览器响应拦截，将示例成绩响应中的 full_score 置0，页面实际显示 `664/0`、`Infinity%`。此项为边界数据注入验证，未改动数据库；不代表现有示例数据满分为0。

证据：[缺满分截图](qa-recheck-2026-09-16/zero-full-score.png)。应对未知/非正满分显示缺省状态，并停止计算百分比。

### P2：状态管理、错误处理和日志未完整接入

- [StudentPages.tsx:18](../../apps/web/src/pages/StudentPages.tsx:18)、[ManagementPages.tsx:15](../../apps/web/src/pages/ManagementPages.tsx:15)、[App.tsx:42](../../apps/web/src/App.tsx:42) 仍各自加载服务器数据。统一 hooks 的存在不等于页面已迁移。
- 统一 ErrorDisplay 仅用于 `/profile`；其他学生页仍是普通错误文本，管理操作仍有 alert，ErrorBoundary 没有挂载。拦截网络失败后概览显示 `Failed to fetch`，见[断网截图](qa-recheck-2026-09-16/network-error.png)。
- [main.py:143](../../apps/api/app/main.py:143) 只注册 FastAPI HTTPException，隔离请求不存在路由及错误方法分别得到 `{"detail":"Not Found"}`、`{"detail":"Method Not Allowed"}`，没有统一 error 对象。
- [logging.py:43](../../apps/api/app/core/logging.py:43) 使用 PrintLoggerFactory，绕过标准 logging 的文件 Handler。隔离复现：业务 JSON 只写 stdout，配置的文件没有业务事件；标准 logging 写入文件的内容是纯文本。
- 日志处理器未渲染异常，`logger.exception` 实测只有 `"exc_info":true`，没有堆栈；[logging.py:41](../../apps/api/app/core/logging.py:41) 固定 INFO，配置 ERROR 后 INFO 仍输出；bind_context 没有调用，无法统一关联 request_id。

## 查询与测试结果

N+1专项使用独立内存数据库，构造1和50条学校/学生记录，学生列表、学校列表均为3次 SELECT，未随条数线性增长。成绩首页6次 SELECT、趋势2次，示例88/100科目数据返回正确。此结果证明所检查端点源码中的查询次数受控，不等于已做真实 PostgreSQL 大数据压测，也不能推出“速度提升67倍”。旧学生列表原本也是3次查询，已有修复报告里的201→3缺乏依据。

| 验证 | 结果 |
| --- | --- |
| 后端现有全套测试，SQLite内存数据库 | 57通过，0失败，1条依赖弃用警告 |
| 前端 lint | 通过 |
| 前端现有单测 | 1通过；仅验证 API 基地址 |
| 前端生产构建 | 通过；JS 675.44kB，gzip 201.06kB，有包体积告警 |
| 现有 E2E 收集 | 52用例/8文件；本次未执行整套52用例 |
| 浏览器专项验证 | 执行真实登录、账号切换、成绩与图表、4种窄视口、网络故障、满分边界及部署路由检查 |

现有自动化不能作为本次全部通过的证明：

- 52个 E2E 中没有 `/profile`，图表测试检查旧 `/trends` 容器；部分科目/考试数断言允许 `>=0`。
- [performance.spec.ts:17](../../tests/e2e/performance.spec.ts:17) 实际阈值为3000ms，不是2000ms。
- [.github/workflows/e2e-tests.yml:65](../../.github/workflows/e2e-tests.yml:65) 在 apps/web 执行 E2E，却未指定根目录配置；按该目录及参数实测收集报 `Project(s) "chromium" not found`。CI矩阵还包含未配置的 Firefox/WebKit。
- 原 E2E 报告自述13/52已通过、其余主要项目待测，却声称覆盖率达标；原“Bug全部修复”结论与本次运行证据不符。

## 性能测量口径

使用当前源码生产构建，在独立本机4179端口临时提供静态页面，并代理到原80端口后端。Chromium桌面1440×1000，禁用浏览器HTTP缓存，连续5次完整导航至 `/profile`，不把登录操作计入页面加载。未使用开发服务器的构建时间作为生产加载时间。

成绩内容及图表路径首次出现：**186.1、167.9、161.8、185.1、158.8ms**。在这个本机条件下，首次内容可见满足2秒。

图表动画稳定确认记录为2020.7–2059.0ms，其中包含额外250ms不变确认等待；不能把这一值直接作为“动画超过2秒”的失败结论。该测试也不是LCP或真实手机弱网测量。

未对正式部署的新版本、真实网络、并发访问和大数据量作性能验收；现有部署仍是旧版。因此整体“加载时间<2s”保留为有限条件通过，待部署一致后补充性能门禁。

原始记录：[性能结果](qa-recheck-2026-09-16/perf-results.json)。

## 建议处理顺序

1. 修复账号隔离及退出时缓存清理，加入账号切换回归。
2. 修复雷达图、样式范围、缺满分及320px布局问题。
3. 完成旧页面查询和错误展示迁移，补齐框架错误与日志输出链路。
4. 增加 `/profile` 的真实数据、图表、移动端、<2s验证，修正CI入口。
5. 构建并部署同一版本，再验证真实入口；以实测结果更新旧验收报告。

附加源码发现：dashboard取最近6条后将其长度当成全部考试次数（platform.py:127/200）；总分趋势升序后limit20导致第21次起最新考试不进入曲线（platform.py:217）；科目按原始分数排序而首页文案写按得分率（platform.py:142）。这些数据口径问题也应纳入后续修复；本次未向真实数据库注入大量考试。
