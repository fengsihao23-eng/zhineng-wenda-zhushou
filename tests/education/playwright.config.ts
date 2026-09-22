import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "..",
  testMatch: [
    "**/alignment/alignment.spec.ts",
    "**/education/*.spec.ts",
  ],
  workers: 1,
  timeout: 45000,
  reporter: [["list"]],
  outputDir: process.env.QA_OUTPUT_DIR || "/tmp/qa-education-browser",
  use: {
    baseURL: "http://127.0.0.1:5208",
    ...devices["Desktop Chrome"],
    trace: "off",
    video: "off",
    screenshot: "only-on-failure",
  },
});
