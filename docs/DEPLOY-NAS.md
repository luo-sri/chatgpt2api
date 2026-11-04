# NAS 部署指南（飞牛 fnOS / 群晖 Synology）

本文以飞牛 fnOS 为主，群晖部分在末尾。
原理相同：Docker 容器 + 三端口映射 + 一个数据目录。

---

## 一、前置条件

| 项 | 要求 |
|---|---|
| NAS 系统 | 飞牛 fnOS / 群晖 DSM 7.x / TrueNAS 等 |
| Docker | 已安装（fnOS 自带「Docker」应用，需在应用中心启用） |
| 架构 | x86_64（arm 机型需自行确认基础镜像是否支持） |
| 内存 | 建议 2 GB 以上可用 |
| 磁盘 | 3 GB 以上 |

### 检查 SSH

fnOS：**系统设置 → 远程访问 → 开启 SSH**

```bash
ssh 你的用户名@NAS的IP
sudo -i
```

---

## 二、方式 A：图形界面（最简单）

### 1. 创建目录

用「文件管理」在存储空间里建一个新文件夹，例如：

```
/vol1/1000/docker/chatgpt2api
```

把项目文件传进去（可以用 SMB / 文件管理的上传功能）。

### 2. 导入镜像

如果 NAS 能联网且能访问 Docker Hub / ghcr.io，可跳过这步，
compose 会自动拉取。

否则先在**你自己的电脑上**构建并导出：

```bash
# 本机（项目目录内）
docker build -t chatgpt2api-allinone:latest .

# 导出
docker save chatgpt2api-allinone:latest -o allinone.tar.gz

# 传到 NAS
scp allinone.tar.gz 用户名@NAS-IP:/vol1/1000/docker/
```

NAS 上导入：

```bash
docker load < /vol1/1000/docker/allinone.tar.gz
```

### 3. 在图界面里创建容器

fnOS「Docker」应用 →「容器」→「新增」→「从 compose 创建」：

粘贴项目里的 `docker-compose.yml` 内容，按需改端口。

或选「手动创建」，逐项填：

| 项 | 值 |
|---|---|
| 镜像 | `chatgpt2api-allinone:latest` |
| 容器名 | `chatgpt2api-allinone` |
| 重启策略 | `unless-stopped` |
| 端口 | `3100:3000`、`8888:8888`、`6080:6080` |
| 环境变量 | `CHATGPT2API_AUTH_KEY=你的密码`、`TZ=Asia/Shanghai` |
| 卷映射 | `/vol1/1000/docker/chatgpt2api/data` → `/app/data` |
| | `.../config.json` → `/app/config.json` |
| | `.../mihomo-config.yaml` → `/root/.config/mihomo/config.yaml` |

### 4. 启动并访问

```
http://NAS的IP:3100
```

---

## 三、方式 B：SSH 命令行（推荐，可控）

### 1. 传到 NAS

```bash
# 在你电脑上
scp -r chatgpt2api 用户名@NAS-IP:/vol1/1000/docker/
```

### 2. 登录 NAS

```bash
ssh 用户名@NAS-IP
sudo -i
cd /vol1/1000/docker/chatgpt2api
```

### 3. 配置

```bash
cp .env.example .env
vi .env
```

改成：

```ini
CHATGPT2API_AUTH_KEY=你的密码
TZ=Asia/Shanghai
```

### 4. 启动

```bash
# 能联网拉基础镜像
docker compose up -d --build

# 或已导入本地镜像
docker compose up -d
```

### 5. 确认

```bash
docker compose ps
docker compose logs --tail 30
```

看到 `===== ALL READY =====` 即成功。

---

## 四、端口冲突处理

NAS 上 3000 常被其他服务占用（如 New API、青龙）。

### 改 compose

```yaml
ports:
  - "13100:3000"    # 改成 NAS 上空闲的端口
  - "18888:8888"
  - "16080:6080"
```

重启后访问：

```
http://NAS的IP:13100
```

对应地，客户端 Base URL 也要改成 `http://NAS的IP:13100/v1`。

### 查端口占用

```bash
netstat -tulpn | grep 3000
```

或 fnOS 图形界面「Docker → 容器」里看已用端口。

---

## 五、飞牛 fnOS 特有事项

### 应用中心启用 Docker

**应用中心 → 搜索 "Docker" → 安装 → 启用**

### 存储路径

fnOS 的存储空间通常挂载在 `/vol1/`，用户目录 `/vol1/1000/`。
建议放：

```
/vol1/1000/docker/chatgpt2api
```

### 开机自启

compose 里已写 `restart: unless-stopped`，NAS 重启后容器会自动启动。

不放心可以在 fnOS「Docker → 容器 → 设置」里确认「自动重启」已开。

### 外网访问

fnOS 自带内网穿透 / DDNS。如果用：

1. **务必先改掉默认密钥**
2. 建议只暴露 3100，且加一层 HTTPS 反代
3. 不要直接暴露 6080（内置浏览器画面），有安全风险

---

## 六、群晖 Synology 要点

### 1. 安装 Container Manager

套件中心 → 搜索「Container Manager」→ 安装

### 2. 目录

```
/volume1/docker/chatgpt2api
```

### 3. 用「项目」功能

Container Manager →「项目」→「新增」→ 上传 `docker-compose.yml`
→ 选择上面的目录 → 构建

### 4. 权限

群晖的 docker 目录需要给 `docker` 用户读写权限：

```bash
sudo chown -R 1000:1000 /volume1/docker/chatgpt2api/data
```

否则容器写不进 `data/`，账号存不下来。

### 5. DSM 7 的 SSH

控制面板 → 终端机和 SNMP → 启用 SSH 功能

---

## 七、ARM 机型说明

本项目基础镜像 `ghcr.io/basketikun/chatgpt2api` 主要面向 x86_64。
ARM（如部分群晖 DS220j、树莓派）可能拉不到镜像或运行异常。

解决思路：

1. 在 x86 机器上构建并 `docker save` 导出，再到 ARM 上 `docker load`
   （前提是基础镜像有多架构版本）
2. 或改用 x86 的 NAS / 小主机

---

## 八、离线部署（NAS 无外网）

### 在有网的机器上准备

```bash
# 1. 构建
docker build -t chatgpt2api-allinone:latest .

# 2. 导出（镜像 + 基础依赖一起打进去）
docker save chatgpt2api-allinone:latest | gzip > allinone.tar.gz

# 3. 打包项目（不要带 data/）
tar --exclude='data' -czf chatgpt2api-src.tar.gz chatgpt2api/
```

### 拷贝到 NAS

```bash
scp allinone.tar.gz chatgpt2api-src.tar.gz 用户名@NAS-IP:/vol1/1000/docker/
```

### NAS 上部署

```bash
cd /vol1/1000/docker
mkdir -p chatgpt2api && cd chatgpt2api
tar -xzf ../chatgpt2api-src.tar.gz --strip-components=1
docker load < ../allinone.tar.gz
cp .env.example .env && vi .env
docker compose up -d
```

> 离线环境下**代理订阅仍然需要外网**才能更新（节点信息来自机场服务器）。
> 如果 NAS 完全无外网，需要在有网机器上更新订阅后，
> 把 `data/` 目录一起拷过去。

---

## 九、性能与资源

内置浏览器（Chromium + Xvfb）比较吃内存：

| 使用场景 | 建议内存 |
|---|---|
| 只用 API，不加账号 | 1 GB |
| 加账号时要开浏览器 | 2 GB |
| 长期挂着 + 多账号 | 4 GB |

可以在 compose 里限制：

```yaml
deploy:
  resources:
    limits:
      memory: 2G
```

`shm_size` 建议给 512MB 以上（Chromium 需要）：

```yaml
shm_size: 512mb
```

---

## 十、常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| `docker load` 报错 | tar 包损坏 | 重新导出；检查传输是否完整 |
| 容器起不来，日志显示权限错误 | data 目录权限不对 | `chown -R 1000:1000 data/` |
| 页面能开，加账号弹窗空白 | 6080 没映射 | compose 加 `-p 6080:6080` |
| 内置浏览器黑屏 | shm 太小 | 加 `shm_size: 512mb` |
| 重启后账号丢了 | data 没挂载 | 检查 volumes 是否指向宿主机目录 |
| 节点全红 | NAS 无法访问机场域名 | 检查 NAS 的 DNS / 网络策略 |

---

## 下一步

- [Docker 通用指南](DEPLOY-DOCKER.md)
- [Linux 服务器部署](DEPLOY-LINUX.md)
- [API 文档](API.md)
- [常见问题](FAQ.md)
