#!/bin/sh
# ============================================================
#  一体化容器启动
#    mihomo      : 内部 7890 / 9090
#    chatgpt2api : 内部 3001
#    网关+WebUI  : 对外 3000
#    授权代理     : 对外 8888
# ============================================================
set -e

echo "[start] ===== ChatGPT2API All-in-One ====="

# ---------- mihomo ----------
if [ ! -f /root/.config/mihomo/config.yaml ] && [ -f /opt/mihomo-config.yaml ]; then
  echo "[start] 使用内置代理配置"
  mkdir -p /root/.config/mihomo
  cp /opt/mihomo-config.yaml /root/.config/mihomo/config.yaml
fi

if [ -f /usr/local/bin/mihomo ] && [ -f /root/.config/mihomo/config.yaml ]; then
  echo "[start] mihomo ..."
  /usr/local/bin/mihomo -d /root/.config/mihomo -f /root/.config/mihomo/config.yaml \
    >/app/data/mihomo.log 2>&1 &
  for i in $(seq 1 40); do
    if python -c "import urllib.request as u;u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:9090/version',timeout=2)" 2>/dev/null; then
      echo "[start] mihomo ready"; break
    fi
    sleep 1
  done
else
  echo "[start] mihomo 配置缺失，跳过"
fi

# ---------- 前端包补丁（幂等）----------
# 把「新窗口打开授权页」改成项目内弹窗、把三个入口写进原生导航数组。
# 放在启动时做，容器重建后自动生效，不需要重新 build 镜像。
if [ -f /opt/gateway/patch_webdist.py ]; then
  python /opt/gateway/patch_webdist.py || echo "[start] 前端包补丁失败（不影响启动）"
fi

# ---------- chatgpt2api ----------
echo "[start] chatgpt2api on 3001 ..."
cd /app
# 直接用已装好的 venv，避免 uv 在离线环境尝试联网同步依赖
/app/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 3001 --access-log \
  >/app/data/app.log 2>&1 &

for i in $(seq 1 90); do
  if python -c "import urllib.request as u;u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:3001/version',timeout=2)" 2>/dev/null; then
    echo "[start] chatgpt2api ready"; break
  fi
  sleep 1
done

# ---------- 网关（含 WebUI + 授权代理） ----------
echo "[start] gateway on 3000 ..."
cd /opt/gateway
sed -i "s|^base_url.*|base_url = http://127.0.0.1:3001|" config.ini
python gateway.py >/app/data/gateway.log 2>&1 &

for i in $(seq 1 40); do
  if python -c "import urllib.request as u;u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:3000/health',timeout=2)" 2>/dev/null; then
    echo "[start] gateway ready"; break
  fi
  sleep 1
done

sh /opt/backup.sh >/dev/null 2>&1 &

# 内置浏览器（noVNC 6080）：加账号时在这登录，走容器代理
if [ -x /opt/browser.sh ]; then
  echo "[start] 内置浏览器 ..."
  sh /opt/browser.sh >/app/data/browser-start.log 2>&1 &
fi


# 兼容旧地址：容器内 13001 转发到网关（compose 再把宿主的 3001 映射到它），避免用户访问旧端口时 ERR_CONNECTION_REFUSED
python - <<'PYFWD' >/app/data/fwd.log 2>&1 &
import socket, threading
def pipe(a, b):
    try:
        while True:
            d = a.recv(65536)
            if not d: break
            b.sendall(d)
    except Exception: pass
    finally:
        try: a.close()
        except Exception: pass
        try: b.close()
        except Exception: pass
def handle(c):
    try:
        u = socket.create_connection(("127.0.0.1", 3000), timeout=10)
        threading.Thread(target=pipe, args=(c,u), daemon=True).start()
        threading.Thread(target=pipe, args=(u,c), daemon=True).start()
    except Exception:
        try: c.close()
        except Exception: pass
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", 13001))
srv.listen(64)
while True:
    try:
        c,_ = srv.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()
    except Exception: pass
PYFWD
echo "[start] 3001 转发到 3000（兼容旧地址）"

echo "[start] ===== ALL READY ====="
echo "  控制台 : http://<host>:3000/"
echo "  API    : http://<host>:3000/v1"
echo "  内置浏览器: http://<host>:6080/vnc.html?autoconnect=1&resize=remote"
echo "  授权代理  : 127.0.0.1:8888"

# 保活：用健康检查判断，不依赖 pgrep（精简镜像可能没有）
while true; do
  sleep 20
  if ! python -c "import urllib.request as u;u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:3000/health',timeout=3)" 2>/dev/null; then
    echo "[start] gateway 无响应，退出让 docker 重启"; exit 1
  fi
done
