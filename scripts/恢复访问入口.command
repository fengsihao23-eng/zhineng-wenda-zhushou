#!/bin/bash
# Double-click this file in Finder after reboot or wake to renew both URLs.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:$HOME/.docker/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
cd "$ROOT" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 "$ROOT/scripts/restore_access.py"
  result=$?
else
  echo "未找到 Python 3，请先安装 Python 3。"
  result=1
fi
if [[ -t 0 && "${RESTORE_ACCESS_NO_PAUSE:-}" != "1" ]]; then
  echo
  read -r -p "按回车键关闭窗口；新地址也保存在桌面‘知行最新访问地址.txt’中…" _
fi
exit "$result"
