# -*- coding: utf-8 -*-
"""一体化容器入口

顺序：
  1. 启动 mihomo（后台）
  2. 等待 7890/9090 就绪
  3. 启动 chatgpt2api（前台）
  4. 同时启动控制台 8080
"""
import os
import subprocess
import sys
import threading
import time
import urllib.request

MIHOMO_BIN = "/usr/local/bin/mihomo"
MIHOMO_CONF = "/root/.config/mihomo/config.yaml"
APP_DIR = "/app"
CONSOLE_PORT = 8080


def wait_port(port, path="/version", timeout=90):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    end = time.time() + timeout
    while time.time() < end:
        try:
            op.open(f"http://127.0.0.1:{port}{path}", timeout=3).read()
            return True
        except Exception:
            time.sleep(1)
    return False


def main():
    # 1) mihomo
    if os.path.exists(MIHOMO_BIN) and os.path.exists(MIHOMO_CONF):
        print("[entry] starting mihomo ...", flush=True)
        subprocess.Popen([MIHOMO_BIN, "-d", "/root/.config/mihomo",
                          "-f", MIHOMO_CONF],
                         stdout=sys.stdout, stderr=sys.stderr)
        if wait_port(9090, "/version", 60):
            print("[entry] mihomo ready", flush=True)
        else:
            print("[entry] WARNING: mihomo not ready", flush=True)
    else:
        print("[entry] mihomo binary/config missing, skip", flush=True)

    # 2) 控制台（后台线程）
    try:
        sys.path.insert(0, "/opt/console")
        import console
        threading.Thread(target=console.start_console_server, daemon=True).start()
        print(f"[entry] console on :{CONSOLE_PORT}/console", flush=True)
    except Exception as e:
        print(f"[entry] console failed: {e}", flush=True)

    # 3) chatgpt2api（前台，容器主进程）
    os.chdir(APP_DIR)
    print("[entry] starting chatgpt2api ...", flush=True)
    os.execvp("python", ["python", "main.py"])


if __name__ == "__main__":
    main()
