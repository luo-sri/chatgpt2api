# -*- coding: utf-8 -*-
"""本地授权转发代理

在本机监听 8888，把所有 HTTP/HTTPS 请求转给 mihomo（127.0.0.1:7890）。
用户只要把浏览器代理指向 127.0.0.1:8888，就能打开 OpenAI 授权页，
本机系统代理完全不用动。

支持 CONNECT 隧道（HTTPS 必需）。
"""
import select
import socket
import threading


import os

UPSTREAM_HOST = os.environ.get("AUTH_PROXY_UPSTREAM", "127.0.0.1")
UPSTREAM_PORT = int(os.environ.get("AUTH_PROXY_UPSTREAM_PORT", "7890"))
LISTEN_PORT = int(os.environ.get("AUTH_PROXY_PORT", "8888"))
# 容器里必须是 0.0.0.0 才能被宿主访问；本机保持 127.0.0.1
LISTEN_HOST = os.environ.get("AUTH_PROXY_BIND", "127.0.0.1")


def pipe(a, b):
    try:
        while True:
            r, _, _ = select.select([a, b], [], [], 60)
            if not r:
                break
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    except Exception:
        pass
    finally:
        try:
            a.close()
        except Exception:
            pass
        try:
            b.close()
        except Exception:
            pass


def handle(client):
    try:
        client.settimeout(30)
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = client.recv(65536)
            if not chunk:
                client.close()
                return
            head += chunk
            if len(head) > 65536:
                break

        first = head.split(b"\r\n", 1)[0].decode("latin-1")
        method = first.split(" ")[0] if " " in first else ""

        upstream = socket.create_connection((UPSTREAM_HOST, UPSTREAM_PORT), timeout=20)

        if method.upper() == "CONNECT":
            # 直接把 CONNECT 交给 mihomo，它负责建隧道
            upstream.sendall(head)
            client.settimeout(None)
            upstream.settimeout(None)
            pipe(client, upstream)
            return

        # 普通 HTTP：整段转发（mihomo 作为上游代理会处理）
        upstream.sendall(head)
        client.settimeout(None)
        upstream.settimeout(None)
        pipe(client, upstream)
    except Exception:
        try:
            client.close()
        except Exception:
            pass


def serve():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(128)
    print(f"[auth-proxy] {LISTEN_HOST}:{LISTEN_PORT} -> {UPSTREAM_HOST}:{UPSTREAM_PORT}",
          flush=True)
    while True:
        try:
            c, _ = srv.accept()
            threading.Thread(target=handle, args=(c,), daemon=True).start()
        except Exception:
            continue


def start_in_thread():
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    serve()
