"""Recover the two local macOS Quick Tunnels; never print credentials.

Run via 恢复访问入口.command. Quick Tunnel hostnames are disposable, so each
manual recovery restarts both connectors and publishes only verified new URLs.
"""
from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local" / "yjyz-roster"
AGENTS = Path.home() / "Library" / "LaunchAgents"
GUI = f"gui/{os.getuid()}"
DOCKER_LABEL = "com.zhinengqa.docker-quick-tunnel"
DOCKER_PLIST = AGENTS / f"{DOCKER_LABEL}.plist"
PREVIEW_LABEL = "com.codex.yjyz.roster-preview"
GATEWAY_LABEL = "com.codex.yjyz.manager-gateway"
PREVIEW_TUNNEL_LABEL = "com.codex.yjyz.manager-tunnel"
URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
METRICS_PATTERN = re.compile(r"Starting metrics server on 127\.0\.0\.1:(\d+)/metrics")


def run(*args: str, timeout: int = 20, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"命令失败：{Path(args[0]).name} {args[1]}（{(result.stderr or result.stdout).strip()[-250:]}）")
    return result


def wait_until(predicate, seconds: int, description: str) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(2)
    raise RuntimeError(f"{description}未就绪，请稍后双击脚本重试。")


def local_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=4) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def ensure_docker() -> None:
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("未找到 Docker 命令，请先安装或启动 Docker Desktop。")
    if run(docker, "info", check=False).returncode:
        print("Docker Desktop 未运行，正在启动…", flush=True)
        run("open", "-a", "Docker")
        wait_until(lambda: run(docker, "info", check=False).returncode == 0, 150, "Docker Desktop")
    print("检查 Docker Compose 服务…", flush=True)
    run(docker, "compose", "up", "-d", "--wait", "--wait-timeout", "120", timeout=240)
    wait_until(lambda: local_ok("http://127.0.0.1/api/v1/health"), 30, "Docker 主站")
    print("Docker 主站已就绪。", flush=True)


def loaded(label: str) -> bool:
    return run("launchctl", "print", f"{GUI}/{label}", check=False).returncode == 0


def ensure_agent(label: str, plist: Path, healthy_url: str) -> None:
    if not plist.is_file():
        raise RuntimeError(f"缺少本机启动配置：{plist.name}（不会重建私密账号数据）。")
    if not loaded(label):
        run("launchctl", "bootstrap", GUI, str(plist))
    if not local_ok(healthy_url):
        run("launchctl", "kickstart", "-k", f"{GUI}/{label}")
    wait_until(lambda: local_ok(healthy_url), 120, label)


def ensure_preview() -> None:
    ensure_agent(PREVIEW_LABEL, AGENTS / f"{PREVIEW_LABEL}.plist", "http://127.0.0.1:61564/api/v1/health")
    ensure_agent(GATEWAY_LABEL, AGENTS / f"{GATEWAY_LABEL}.plist", "http://127.0.0.1:61565/__manager_access")
    print("档案预览和访问网关已就绪。", flush=True)


def create_docker_agent() -> bool:
    cloudflared = shutil.which("cloudflared")
    if not cloudflared:
        raise RuntimeError("未找到 cloudflared，请先安装 cloudflared。")
    AGENTS.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if DOCKER_PLIST.exists():
        config = plistlib.loads(DOCKER_PLIST.read_bytes())
        if config.get("Label") != DOCKER_LABEL or "http://127.0.0.1:80" not in config.get("ProgramArguments", []):
            raise RuntimeError("Docker 隧道启动配置被修改，未自动覆盖；请人工检查 LaunchAgents。")
        return False
    config = {
        "Label": DOCKER_LABEL,
        "ProgramArguments": [cloudflared, "tunnel", "--url", "http://127.0.0.1:80", "--metrics", "127.0.0.1:20661"],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(STATE / "docker-tunnel-launchd.log"),
        "StandardErrorPath": str(STATE / "docker-tunnel-launchd.err.log"),
    }
    DOCKER_PLIST.write_bytes(plistlib.dumps(config))
    DOCKER_PLIST.chmod(0o644)
    return True


def stop_legacy_docker_tunnels() -> None:
    # On the first run, migrate the old manually started tunnel to launchd.
    output = run("ps", "-axo", "pid=,command=").stdout
    for line in output.splitlines():
        match = re.match(r"\s*(\d+)\s+(.*)", line)
        if not match:
            continue
        pid, command = int(match[1]), match[2]
        if pid != os.getpid() and "cloudflared tunnel --url http://localhost:80" in command:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def ready_connections(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=3) as response:
            return response.status == 200 and json.load(response).get("readyConnections", 0) > 0
    except (OSError, ValueError, urllib.error.URLError):
        return False


def new_tunnel(label: str, log: Path, old_size: int, fixed_port: int | None = None) -> str:
    if not loaded(label):
        run("launchctl", "bootstrap", GUI, str(AGENTS / f"{label}.plist"))
    else:
        run("launchctl", "kickstart", "-k", f"{GUI}/{label}")
    # Only trust a URL logged after this invocation, never an expired hostname.
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        text = log.read_text(errors="replace") if log.exists() else ""
        tail = text[old_size:] if len(text) >= old_size else text
        urls = URL_PATTERN.findall(tail)
        metrics = METRICS_PATTERN.findall(tail)
        port = fixed_port or (int(metrics[-1]) if metrics else None)
        if urls and port and "Registered tunnel connection" in tail and ready_connections(port):
            return urls[-1]
        time.sleep(2)
    raise RuntimeError(f"{label} 尚未连接 Cloudflare；检查日志 {log}。")


def proxy_works(port: int = 7890) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def public_ok(site: str, url: str) -> bool:
    handlers = [urllib.request.ProxyHandler()]
    if proxy_works():
        handlers.append(urllib.request.ProxyHandler({"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}))
    for handler in handlers:
        try:
            opener = urllib.request.build_opener(handler)
            with opener.open(url + "/login", timeout=8) as response:
                body = response.read(20_000).decode(errors="replace")
                if site == "preview":
                    if "访问口令" in body and "/__manager_access" in response.url:
                        return True
                elif response.status == 200 and "/assets/index-" in body:
                    with opener.open(url + "/api/v1/health", timeout=8) as health:
                        return json.load(health).get("status") == "ok"
        except (OSError, ValueError, urllib.error.URLError):
            continue
    return False


def main() -> None:
    print("恢复知行访问入口（不会重建或清空数据库）\n", flush=True)
    ensure_docker()
    ensure_preview()
    created = create_docker_agent()
    if created:
        stop_legacy_docker_tunnels()
    docker_log = STATE / "docker-tunnel-launchd.err.log"
    preview_log = STATE / "manager-tunnel-launchd.err.log"
    docker_offset = len(docker_log.read_text(errors="replace")) if docker_log.exists() else 0
    preview_offset = len(preview_log.read_text(errors="replace")) if preview_log.exists() else 0
    print("重新建立临时隧道…", flush=True)
    main_url = new_tunnel(DOCKER_LABEL, docker_log, docker_offset, fixed_port=20661)
    preview_url = new_tunnel(PREVIEW_TUNNEL_LABEL, preview_log, preview_offset)
    print("正在核对外网访问…", flush=True)
    deadline = time.monotonic() + 60
    checks = {"main": False, "preview": False}
    while time.monotonic() < deadline and not all(checks.values()):
        for site, url in [("main", main_url), ("preview", preview_url)]:
            if not checks[site]:
                checks[site] = public_ok(site, url)
        if not all(checks.values()):
            time.sleep(3)
    if not all(checks.values()):
        failed = "、".join(site for site, ok in checks.items() if not ok)
        raise RuntimeError(f"隧道已注册，但{failed}外网访问未能核实；请稍后重试，不要使用旧链接。")
    lines = ["知行最新访问地址（临时隧道，每次恢复可能变更）", "", f"Docker 主站：{main_url}/login",
             f"师生档案预览：{preview_url}/login", "", "预览入口仍需原访问口令；此文件不保存账号或密码。"]
    text = "\n".join(lines) + "\n"
    target = Path.home() / "Desktop" / "知行最新访问地址.txt"
    if target.parent.is_dir():
        target.write_text(text)
        target.chmod(0o600)
    print("\n" + text)
    if target.parent.is_dir():
        print(f"已更新桌面：{target}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"\n恢复失败：{exc}", file=sys.stderr)
        sys.exit(1)
