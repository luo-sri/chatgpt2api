#!/bin/sh
# ============================================================
#  容器内置浏览器（noVNC）
#
#  Xvfb 虚拟屏幕 → Chromium（走容器内 7890 代理）→ x11vnc → noVNC(6080)
#  这样你在浏览器里打开 http://<host>:6080 就能操作容器内的浏览器，
#  登录 OpenAI 时流量走容器代理，本机不需要开任何代理。
#
#  幂等：可重复执行。每次启动前清掉上次残留的 X 锁与 Chromium 档案锁，
#  否则容器重启后 Xvfb 会因 "Server is already active for display 99" 退出，
#  Chromium 会弹 "profile appears to be in use"，画面就黑屏了。
# ============================================================
set -e

DISPLAY_NUM=":99"
DISP_NUM="99"
SCREEN="1440x900x24"
VNC_PORT=5900
NOVNC_PORT=6080
PROFILE="/app/data/chrome-profile"

export DISPLAY="$DISPLAY_NUM"

# ---------- 0. 清理上次残留 ----------
# 已有旧进程就先干掉，避免端口占用
pkill -f "Xvfb $DISPLAY_NUM" 2>/dev/null || true
pkill -f "chrome-profile" 2>/dev/null || true
pkill -f "x11vnc -display" 2>/dev/null || true
pkill -f "websockify --web" 2>/dev/null || true
sleep 1
rm -f "/tmp/.X${DISP_NUM}-lock" "/tmp/.X11-unix/X${DISP_NUM}"
rm -f "$PROFILE/SingletonLock" "$PROFILE/SingletonCookie" "$PROFILE/SingletonSocket"

# ---------- 1. 虚拟屏幕 ----------
echo "[browser] Xvfb $SCREEN ..."
Xvfb "$DISPLAY_NUM" -screen 0 "$SCREEN" -ac +extension GLX +render -noreset \
  >/app/data/xvfb.log 2>&1 &

# 等到 X socket 真正可连（最多 15 秒）
X_OK=0
for i in $(seq 1 30); do
  if [ -S "/tmp/.X11-unix/X${DISP_NUM}" ]; then X_OK=1; break; fi
  sleep 0.5
done
if [ "$X_OK" != "1" ]; then
  echo "[browser] Xvfb 启动失败，见 /app/data/xvfb.log"
  tail -3 /app/data/xvfb.log 2>/dev/null
  exit 0
fi
echo "[browser] X 屏幕就绪"

# ---------- 2. 等容器代理 7890 就绪 ----------
for i in $(seq 1 40); do
  if python -c "
import socket,sys
s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1',7890))==0 else 1)
" 2>/dev/null; then
    echo "[browser] proxy 7890 ready"
    break
  fi
  sleep 1
done

# ---------- 3. Chromium ----------
CHROME_BIN=$(which chromium 2>/dev/null || which chromium-browser 2>/dev/null)
if [ -z "$CHROME_BIN" ]; then
  echo "[browser] 找不到 chromium，跳过"
  exit 0
fi

mkdir -p "$PROFILE"
echo "[browser] Chromium ..."
"$CHROME_BIN" \
  --no-sandbox --disable-gpu --disable-dev-shm-usage \
  --proxy-server="http://127.0.0.1:7890" \
  --proxy-bypass-list="<-loopback>" \
  --ignore-certificate-errors \
  --disable-ipv6 \
  --remote-debugging-port=9222 --remote-allow-origins=* \
  --window-size=1440,900 --window-position=0,0 \
  --no-first-run --no-default-browser-check \
  --disable-features=Translate,MediaRouter \
  --user-data-dir="$PROFILE" \
  --lang=zh-CN \
  "https://chatgpt.com/" \
  >/app/data/chrome.log 2>&1 &

# ---------- 4. VNC ----------
echo "[browser] x11vnc ..."
x11vnc -display "$DISPLAY_NUM" -rfbport $VNC_PORT -forever -shared -nopw -quiet \
  -xkb -repeat >/app/data/x11vnc.log 2>&1 &
sleep 2

echo "[browser] noVNC on $NOVNC_PORT ..."
NOVNC_WEB=""
for d in /usr/share/novnc /usr/share/webapps/novnc /usr/share/noVNC; do
  if [ -f "$d/vnc.html" ]; then NOVNC_WEB="$d"; break; fi
done

if [ -n "$NOVNC_WEB" ]; then
  websockify --web "$NOVNC_WEB" "$NOVNC_PORT" "localhost:$VNC_PORT" \
    >/app/data/novnc.log 2>&1 &
  echo "[browser] noVNC ready: http://<host>:$NOVNC_PORT/vnc.html?autoconnect=1&resize=remote"
else
  echo "[browser] 未找到 noVNC 网页目录"
fi
