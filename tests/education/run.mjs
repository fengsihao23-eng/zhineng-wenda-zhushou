/** Isolated production build + synthetic browser journeys. Never loads .env. */
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { createWriteStream } from "node:fs";
import { readFile, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";
const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const scratch = await mkdtemp(path.join(tmpdir(), "education-browser-"));
const python = path.join(root, ".venv/bin/python");
const credential = randomBytes(32).toString("base64url");
const env = {
  ...process.env,
  APP_ENV: "test",
  MODEL_PROVIDER: "fake",
  DATABASE_URL:
    "postgresql+asyncpg://qa_education@127.0.0.1:55449/qa_education",
  LOG_FILE: path.join(scratch, "api.log"),
  PYTHONPATH: path.join(root, "apps/api"),
  JWT_SECRET_KEY: randomBytes(48).toString("hex"),
  SECRET_KEY: randomBytes(48).toString("hex"),
  RATE_LIMIT_PER_MINUTE: "3000",
  RATE_LIMIT_PER_HOUR: "30000",
};
function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: scratch,
      env,
      stdio: ["pipe", "pipe", "pipe"],
      ...options,
    });
    let out = "",
      errors = "";
    let progress = "";
    child.stdout.on("data", (data) => {
      out += data;
      if (args.some((arg) => String(arg).includes("@playwright"))) {
        progress += data;
        const lines = progress.split("\n");
        progress = lines.pop() || "";
        for (const line of lines)
          if (/^\s*(✓|✘|Running|\d+ (passed|failed))/.test(line))
            process.stdout.write(
              line.replaceAll(credential, "[redacted]") + "\n",
            );
      }
    });
    child.stderr.on("data", (data) => {
      errors += data;
    });
    child.on("error", reject);
    child.on("exit", (code) =>
      code === 0
        ? resolve(out)
        : reject(
            Object.assign(new Error(`QA subprocess failed (${code})`), {
              output: (out + errors).replaceAll(credential, "[redacted]"),
            }),
          ),
    );
    child.stdin.end(options.input || "");
  });
}
const safeConfig = path.join(scratch, "vite.config.mjs");
const dist = path.join(scratch, "web");
await writeFile(
  safeConfig,
  `import react from ${JSON.stringify(path.join(root, "apps/web/node_modules/@vitejs/plugin-react/dist/index.js"))};\nexport default {root:${JSON.stringify(path.join(root, "apps/web"))},envDir:${JSON.stringify(scratch)},plugins:[react()],build:{outDir:${JSON.stringify(dist)},emptyOutDir:true},test:{environment:'node'}};\n`,
);
process.stdout.write(`QA artifact directory: ${scratch}\n`);
process.stdout.write(
  await run(process.execPath, [
    path.join(root, "apps/web/node_modules/vitest/vitest.mjs"),
    "run",
    "--config",
    safeConfig,
  ]),
);
process.stdout.write(
  await run(process.execPath, [
    path.join(root, "apps/web/node_modules/vite/bin/vite.js"),
    "build",
    "--config",
    safeConfig,
  ]),
);
const initial = await run(
  python,
  [path.join(root, "tests/alignment/seed.py")],
  { input: credential },
);
const fixture = await run(
  python,
  [path.join(root, "tests/education/enrich.py"), scratch],
  { input: initial },
);
const fixturePath = path.join(scratch, "fixtures.json");
await writeFile(fixturePath, fixture);
const apiLog = createWriteStream(path.join(scratch, "api-startup.log"));
const api = spawn(
  python,
  [
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8028",
    "--workers",
    "2",
    "--no-access-log",
  ],
  { cwd: scratch, env, stdio: ["ignore", "pipe", "pipe"] },
);
api.stdout.pipe(apiLog);
api.stderr.pipe(apiLog);
let ready = false;
for (let i = 0; i < 20; i++) {
  try {
    if (
      (
        await fetch("http://127.0.0.1:8028/api/v1/health", {
          signal: AbortSignal.timeout(1000),
        })
      ).ok
    ) {
      ready = true;
      break;
    }
  } catch {}
  await new Promise((resolve) => setTimeout(resolve, 250));
}
if (!ready) {
  api.kill();
  throw new Error("Isolated API not ready");
}
const server = createServer(async (req, res) => {
  try {
    if (req.url.startsWith("/api/")) {
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      const result = await fetch("http://127.0.0.1:8028" + req.url, {
        method: req.method,
        headers: req.headers,
        body: ["GET", "HEAD"].includes(req.method)
          ? undefined
          : Buffer.concat(chunks),
      });
      const headers = {
        "content-type":
          result.headers.get("content-type") || "application/json",
      };
      const cookies = result.headers.getSetCookie();
      if (cookies.length) headers["set-cookie"] = cookies;
      res.writeHead(result.status, headers);
      res.end(Buffer.from(await result.arrayBuffer()));
      return;
    }
    const urlPath = decodeURIComponent(req.url.split("?")[0]),
      file = path.resolve(dist, "." + urlPath);
    if (!file.startsWith(dist + path.sep) && file !== dist) {
      res.writeHead(403);
      res.end();
      return;
    }
    let content, ext;
    try {
      content = await readFile(file);
      ext = path.extname(file);
    } catch {
      content = await readFile(path.join(dist, "index.html"));
      ext = ".html";
    }
    res.writeHead(200, {
      "content-type":
        {
          ".html": "text/html",
          ".js": "application/javascript",
          ".css": "text/css",
          ".svg": "image/svg+xml",
        }[ext] || "application/octet-stream",
    });
    res.end(content);
  } catch {
    res.writeHead(502);
    res.end("Isolated QA proxy failed");
  }
});
await new Promise((resolve, reject) => {
  server.on("error", reject);
  server.listen(5208, "127.0.0.1", resolve);
});
try {
  process.stdout.write(
    await run(
      process.execPath,
      [
        path.join(root, "node_modules/@playwright/test/cli.js"),
        "test",
        "--config",
        path.join(root, "tests/education/playwright.config.ts"),
      ],
      {
        env: {
          ...env,
          QA_PASSWORD: credential,
          QA_FIXTURE_PATH: fixturePath,
          QA_OUTPUT_DIR: path.join(scratch, "results"),
        },
      },
    ),
  );
} catch (error) {
  process.stdout.write(error.output || error.message);
  process.exitCode = 1;
} finally {
  server.closeAllConnections();
  server.close();
  api.kill("SIGTERM");
  apiLog.end();
}
