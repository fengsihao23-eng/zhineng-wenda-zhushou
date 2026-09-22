# 浏览器回归实测报告

2026-09-17：Chromium **70通过，0失败、0跳过**，共10个测试文件。运行入口为根目录 `npx playwright test --config=playwright.config.ts --project=chromium`，目标为本地生产部署 `http://localhost`。

完整修复清单、测试边界、部署比对与性能实测见 [修复验收记录](QA_FIX_2026-09-17.md)；原始结果见 [E2E结构化结果](qa-fix-2026-09-17/e2e-results.json)。使用方法见 [测试说明](../../tests/e2e/README.md)。

原报告的“13/52通过即可认为覆盖率85%+达标”没有证据支撑，已撤回。当前通过数是测试用例结果，不等于代码覆盖率。聊天回答使用受控SSE；真实模型回答质量、真实手机、外网及并发性能需单独验证。
