# ============================================================
#  ChatGPT2API All-in-One（一体化镜像，含内置浏览器）
#
#  项目主页：https://github.com/luo-sri/chatgpt2api
#  二次开发自：https://github.com/basketikun/chatgpt2api（Apache-2.0）
#
#  端口：
#    3100 -> 3000  API + 控制台（唯一主端口）
#    8888          授权转发代理（备用）
#    6080          内置浏览器（noVNC）—— 加账号时在这里登录，本机无需代理
# ============================================================
# 基础镜像来自上游项目（技术依赖，非本项目品牌）。
# 如需完全自建基础镜像，可把 base 改成自己的 ghcr 仓库后重新构建。
FROM ghcr.io/basketikun/chatgpt2api:latest

LABEL org.opencontainers.image.title="ChatGPT2API All-in-One"
LABEL org.opencontainers.image.description="ChatGPT web accounts to OpenAI-compatible API, with proxy and built-in browser"
LABEL org.opencontainers.image.url="https://github.com/luo-sri/chatgpt2api"
LABEL org.opencontainers.image.source="https://github.com/luo-sri/chatgpt2api"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.version="2.0.0"

USER root

# ---------- 1. 系统依赖 + 内置浏览器 ----------
ENV DEBIAN_FRONTEND=noninteractive
# tiktoken 缓存固定指向容器内目录（预下载好，避免运行时联网被拦）
ENV TIKTOKEN_CACHE_DIR=/app/data/tiktoken-cache
ENV DATA_GYM_CACHE_DIR=/app/data/tiktoken-cache
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        chromium xvfb x11vnc novnc websockify \
        fonts-wqy-zenhei fonts-noto-cjk \
        net-tools xdotool curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* && \
    (which chromium || which chromium-browser) && \
    ls /usr/share/novnc/vnc.html

# ---------- 2. mihomo ----------
COPY --from=docker.1ms.run/metacubex/mihomo:latest /mihomo /usr/local/bin/mihomo
RUN chmod +x /usr/local/bin/mihomo

# ---------- 3. 预置 MMDB（避免启动时联网）----------
RUN mkdir -p /root/.config/mihomo
COPY assets/mihomo/Country.mmdb /root/.config/mihomo/Country.mmdb
COPY assets/mihomo/geosite.dat /root/.config/mihomo/geosite.dat

# ---------- 4. 预装依赖（离线 wheel）----------
COPY assets/wheels/ /tmp/wheels/
RUN uv pip install --python /app/.venv/bin/python \
        --no-index --find-links /tmp/wheels \
        httpx httpcore h11 anyio sniffio idna 2>&1 | tail -3 \
 && /app/.venv/bin/python -c "import httpx, httpcore; print('deps OK')" \
 && rm -rf /tmp/wheels

# ---------- 5. 网关与 WebUI ----------
RUN mkdir -p /opt/gateway /app/data
# 应用代码：app/ 根目录模块 + app/pages/ 页面模块，统一放到 /opt/gateway
COPY app/gateway.py        /opt/gateway/gateway.py
COPY app/webui.py          /opt/gateway/webui.py
COPY app/webapi.py         /opt/gateway/webapi.py
COPY app/console.py        /opt/gateway/console.py
COPY app/entry.py          /opt/gateway/entry.py
COPY app/auth_proxy.py     /opt/gateway/auth_proxy.py
COPY app/jsx_clean.py      /opt/gateway/jsx_clean.py
COPY app/stream_clean.py   /opt/gateway/stream_clean.py
COPY app/cdpeval.py        /opt/gateway/cdpeval.py
COPY app/patch_webdist.py  /opt/gateway/patch_webdist.py
COPY app/pages/chat_page.py     /opt/gateway/chat_page.py
COPY app/pages/proxy_page.py    /opt/gateway/proxy_page.py
COPY app/pages/oauth_page.py    /opt/gateway/oauth_page.py
COPY app/pages/onboarding.py    /opt/gateway/onboarding.py
COPY config.ini            /opt/gateway/config.ini
COPY assets/mihomo-config.yaml /opt/mihomo-config.yaml

COPY scripts/browser.sh /opt/browser.sh
COPY scripts/backup.sh  /opt/backup.sh
COPY scripts/start.sh   /opt/start.sh
RUN chmod +x /opt/start.sh /opt/backup.sh /opt/browser.sh

# 品牌版本号：面板顶部与系统信息读的都是 /app/VERSION
RUN printf '2.0.0' > /app/VERSION

EXPOSE 3000 8888 6080

ENTRYPOINT ["/opt/start.sh"]
