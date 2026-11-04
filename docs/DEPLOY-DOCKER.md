# Docker 通用部署指南

本文适用于任何装有 Docker 的环境（Linux / macOS / Windows / NAS）。
如果你在 Windows 上用 Docker Desktop，也可以先看 [Windows 专用指南](DEPLOY-WINDOWS.md)。

---

## 一、前置要求

| 项 | 要求 |
|---|---|
| Docker | 20.10+ |
| Docker Compose | v2（`docker compose` 命令） |
| 磁盘 | 至少 3 GB 可用（镜像约 1.5 GB） |
| 内存 | 建议 2 GB 以上（内置浏览器较吃内存） |
| 架构 | x86_64 / arm64 |

检查版本：

```bash
docker --version
docker compose version
```

---

## 二、方式 A：docker compose（推荐）

### 1. 获取项目

```bash
git clone https://github.com/luo-sri/chatgpt2api.git
cd chatgpt2api
```

### 2. 配置

```bash
cp .env.example .env
nano .env        # 改成你自己的密钥
```

`.env` 内容：

```ini
# 控制台登录密钥（改成你自己的，8 位以上）
CHATGPT2API_AUTH_KEY=my-secret-2026
# 时区
TZ=Asia/Shanghai
```

### 3. 启动

```bash
docker compose up -d
```

### 4. 检查

```bash
docker compose ps
docker compose logs --tail 30
```

期望看到：

```
[start] ===== ALL READY =====
  控制台 : http://<host>:3000/
  API    : http://<host>:3000/v1
  内置浏览器: http://<host>:6080/vnc.html
```

### 5. 访问

```
http://<服务器IP>:3100
```

---

## 三、方式 B：docker run

不想用 compose，直接一条命令：

```bash
docker run -d \
  --name chatgpt2api-allinone \
  --restart unless-stopped \
  -p 3100:3000 \
  -p 8888:8888 \
  -p 6080:6080 \
  -e TZ=Asia/Shanghai \
  -e CHATGPT2API_AUTH_KEY=my-secret-2026 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config.json:/app/config.json \
  -v $(pwd)/mihomo-config.yaml:/root/.config/mihomo/config.yaml \
  chatgpt2api-allinone:latest
```

前提：先本地构建镜像

```bash
docker build -t chatgpt2api-allinone:latest .
```

Windows PowerShell 里 `$(pwd)` 要换成 `${PWD}` 或绝对路径。

---

## 四、参数详解

### 端口映射

| 宿主机 | 容器 | 说明 |
|---|---|---|
| **3100** | 3000 | 页面 + API + 生图（**唯一主端口**） |
| 8888 | 8888 | 授权转发代理（备用，可不映射） |
| 6080 | 6080 | 内置浏览器画面（加账号需要） |

只映射 3100 也能跑对话和 API，但**加账号必须 6080**。

### 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `CHATGPT2API_AUTH_KEY` | `changeme` | 控制台登录密钥，**务必修改** |
| `TZ` | `Asia/Shanghai` | 时区 |
| `ALL_PROXY` | `http://127.0.0.1:7890` | 容器内代理地址（一般不用改） |
| `NO_PROXY` | `localhost,127.0.0.1` | 不走代理的地址 |

### 数据卷

| 宿主机 | 容器 | 说明 |
|---|---|---|
| `./data` | `/app/data` | **全部状态**：账号、日志、浏览器登录态、节点选择 |
| `./config.json` | `/app/config.json` | 面板配置 |
| `./mihomo-config.yaml` | `/root/.config/mihomo/config.yaml` | 代理配置 |

> `data/` 是命根子。备份它 = 备份一切；删掉它 = 从零开始。

---

## 五、首次配置流程

容器起来后，还需要三步配置（面板里有引导）：

### 1. 配代理订阅

左侧「代理设定」→ 粘贴订阅链接 → 更新订阅 → 选一个节点。

**没有节点什么都用不了**，这一步必做。

### 2. 加账号

左侧「号池管理」→ 导入 → OAuth 登录 → 打开授权页面 →
在内置浏览器里登录 ChatGPT → 自动入库。

### 3. 拿 API Key

左侧「设置」→ 复制 `sk-` 开头的 Key。

然后就能在任意客户端用了：

```
Base URL : http://<IP>:3100/v1
API Key  : sk-xxxx
```

---

## 六、运维

### 日常命令

```bash
docker compose ps                 # 状态
docker compose restart            # 重启
docker compose logs -f            # 实时日志
docker compose logs --tail 100    # 最近 100 行
docker compose down               # 停止（保留数据）
docker compose up -d --build      # 改代码后重建
```

### 更新到新版本

```bash
git pull
docker compose up -d --build
```

`data/` 里的账号和配置都会保留。

### 备份

```bash
# 打包数据
tar -czf backup-$(date +%F).tar.gz data/

# 恢复
tar -xzf backup-2026-01-01.tar.gz
docker compose restart
```

### 迁移到另一台机器

1. 把整个项目目录拷过去（含 `data/`）
2. `docker compose up -d --build`

账号、节点选择、API Key 全部跟着走。

### 完整自检

```bash
python selfcheck.py
```

覆盖 61 项：服务健康、页面路由、API 认证、代理节点、账号池、
OAuth 链路、模型开关、文件完整性。

---

## 七、健康检查

### 手动检查

```bash
# 服务健康
curl http://127.0.0.1:3100/health

# 模型列表（把 sk-xxx 换成你的 Key）
curl http://127.0.0.1:3100/v1/models \
  -H "Authorization: Bearer sk-xxx"

# 代理出口
curl http://127.0.0.1:3100/p/api/proxy | python -m json.tool
```

### Docker 自带的健康检查

容器启动脚本已内置 healthcheck，`docker ps` 会显示 `(healthy)`。
如果不健康，30 秒后自动重启。

---

## 八、常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| `port is already allocated` | 端口被占 | 改 compose 里的宿主机端口 |
| 容器反复重启 | 配置错误 | `docker compose logs --tail 50` |
| 页面能开但对话失败 | 没配节点 / 节点不可用 | 「代理设定」换节点 |
| 加账号弹窗空白 | 6080 没映射 | 补 `-p 6080:6080` |
| 内置浏览器黑屏 | Chromium 未起 | `docker compose restart`，等 40 秒 |
| 生图返回图片打不开 | 用了容器内部地址 | 本项目已自动改写为 3100，若仍异常请更新到最新版 |

---

## 九、卸载

```bash
docker compose down          # 停止并删除容器（保留 data/）
docker rmi chatgpt2api-allinone:latest    # 删镜像
rm -rf data/                 # 删数据（不可恢复）
```

---

## 下一步

- [Windows 部署](DEPLOY-WINDOWS.md)
- [NAS 部署](DEPLOY-NAS.md)
- [Linux 部署](DEPLOY-LINUX.md)
- [API 文档](API.md)
