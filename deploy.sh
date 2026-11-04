#!/bin/sh
# ============================================================
#  ChatGPT2API 一体化部署脚本
#  用法：sudo bash deploy.sh
# ============================================================
set -e

echo "============================================================"
echo "  ChatGPT2API 一体化部署"
echo "============================================================"

# 1. 环境
echo "[1/6] 环境检查"
ARCH=$(uname -m)
[ "$ARCH" = "x86_64" ] || { echo "  需要 x86_64，当前 $ARCH"; exit 1; }
echo "  架构 $ARCH"
command -v docker >/dev/null || { echo "  未安装 Docker"; exit 1; }
echo "  Docker $(docker --version | awk '{print $3}' | tr -d ',')"
docker compose version >/dev/null 2>&1 || { echo "  未安装 docker compose"; exit 1; }

# 2. 端口
echo "[2/6] 端口检查"
PORT_API=${PORT_API:-3000}
PORT_AUTH=${PORT_AUTH:-8888}
for p in $PORT_API $PORT_AUTH; do
  if ss -lnt 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$p\$"; then
    echo "  端口 $p 已被占用，可用 PORT_API=xxxx PORT_AUTH=xxxx 重跑"
    ss -lntp 2>/dev/null | grep ":$p" || true
    exit 1
  fi
done
echo "  $PORT_API / $PORT_AUTH 空闲"

# 3. 目录
echo "[3/6] 准备目录"
APP_DIR=${APP_DIR:-$(pwd)}
mkdir -p "$APP_DIR/data"
[ -f "$APP_DIR/.env" ] || {
  echo "  缺少 .env，正在创建"
  if [ -n "${CHATGPT2API_AUTH_KEY:-}" ]; then
    echo "CHATGPT2API_AUTH_KEY=$CHATGPT2API_AUTH_KEY" > "$APP_DIR/.env"
  else
    read -rsp "  请设置 API 密钥（输入不显示）: " K; echo
    echo "CHATGPT2API_AUTH_KEY=$K" > "$APP_DIR/.env"
  fi
}
chmod 600 "$APP_DIR/.env"
echo "  .env 就绪"
[ -f "$APP_DIR/mihomo-config.yaml" ] || { echo "  缺少 mihomo-config.yaml"; exit 1; }
echo "  代理配置就绪"

# 4. 端口映射
echo "[4/6] 应用端口配置"
if [ "$PORT_API" != "3000" ] || [ "$PORT_AUTH" != "8888" ]; then
  sed -i "s/\"3000:3000\"/\"$PORT_API:3000\"/" docker-compose.yml
  sed -i "s/\"8888:8888\"/\"$PORT_AUTH:8888\"/" docker-compose.yml
fi
grep -E '^\s+- "[0-9]+:[0-9]+"' docker-compose.yml | sed 's/^/  /'

# 5. 构建
echo "[5/6] 构建镜像（首次约 2-3 分钟）"
if docker image inspect chatgpt2api-allinone:latest >/dev/null 2>&1; then
  echo "  镜像已存在，跳过构建"
else
  docker compose build 2>&1 | tail -3
fi

# 6. 启动
echo "[6/6] 启动"
docker compose up -d
echo "  等待服务就绪…"
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$PORT_API/health" >/dev/null 2>&1; then
    echo "  就绪"
    break
  fi
  sleep 3
done

echo
echo "============================================================"
echo "  部署完成"
echo "============================================================"
echo "  控制台   http://$(hostname -I 2>/dev/null | awk '{print $1}'):$PORT_API/"
echo "  API      http://$(hostname -I 2>/dev/null | awk '{print $1}'):$PORT_API/v1"
echo "  授权代理 127.0.0.1:$PORT_AUTH"
echo
echo "  打开控制台 → 添加账号 → 浏览器代理设 127.0.0.1:$PORT_AUTH → 完成登录"
echo "============================================================"
