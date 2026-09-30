#!/bin/bash
# Idempotent host preparation for a fresh Ubuntu 22.04/24.04 cloud server.
# Installs Docker + Compose plugin and sets the timezone. It deliberately does
# not change firewall rules: cloud console security groups stay authoritative.
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "此脚本用于 Linux 云服务器，请勿在本机 macOS 上运行。" >&2
  exit 1
fi

if [[ $EUID -ne 0 ]]; then
  echo "请用 root 运行：sudo bash $0" >&2
  exit 1
fi

echo "1/4 安装基础软件包…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git gnupg >/dev/null

echo "2/4 安装 Docker 与 Compose 插件…"
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
else
  echo "   Docker 已安装，跳过。"
fi
systemctl enable --now docker

echo "3/4 设置时区为 Asia/Shanghai…"
timedatectl set-timezone Asia/Shanghai

echo "4/4 校验…"
docker --version
docker compose version

cat <<'NEXT'

服务器已就绪。下一步：

1. 部署应用（密钥务必替换，不要使用模板占位值）：
     mkdir -p /srv && cd /srv
     git clone https://github.com/fengsihao23-eng/zhineng-wenda-zhushou.git app && cd app
     cp .env.example .env && chmod 600 .env
     docker compose config >/dev/null
     docker compose up -d --build && docker compose ps

2. 创建正式登录账号（生产环境会拦截示例账号）：
     docker compose exec api python scripts/create_school_account.py \
       --school-code <学校代码> --school-name <学校名称> \
       --username admin01 --role SCHOOL_ADMIN

3. 安全组只需放行 22（限定你的 IP）、80、443；数据库与 Redis 不要对公网开放。

4. 配置 HTTPS 与每日备份，见 docs/08-运维与交付/腾讯云部署指南.md。
NEXT
