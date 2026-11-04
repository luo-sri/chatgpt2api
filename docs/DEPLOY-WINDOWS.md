# Windows 部署指南

适用于 Windows 10 / 11，使用 Docker Desktop 运行。

---

## 一、安装 Docker Desktop

1. 打开 <https://www.docker.com/products/docker-desktop/> 下载 Windows 版
2. 双击安装，**勾选 "Use WSL 2 instead of Hyper-V"**（推荐）
3. 安装完成后重启电脑
4. 启动 Docker Desktop，等左下角显示 **Engine running**（绿色）

验证安装：

```powershell
docker --version
# Docker version 24.x.x 或更高
```

> 如果提示 `docker: command not found`，说明 Docker Desktop 没启动，
> 或需要重新打开一个 PowerShell 窗口（环境变量刷新）。

---

## 二、获取项目

### 方式 A：Git（推荐）

```powershell
git clone https://github.com/luo-sri/chatgpt2api.git
cd chatgpt2api
```

### 方式 B：下载 ZIP

到 <https://github.com/luo-sri/chatgpt2api> 点 **Code → Download ZIP**，
解压到任意目录（**路径不要含中文和空格**，例如 `D:\chatgpt2api`）。

---

## 三、配置密钥

```powershell
copy .env.example .env
notepad .env
```

把 `CHATGPT2API_AUTH_KEY` 改成你自己的密码，例如：

```ini
CHATGPT2API_AUTH_KEY=my-secret-2026
TZ=Asia/Shanghai
```

保存后关闭。

> 这个密码用于登录控制台。**API 调用用的是另一个 `sk-` 开头的 Key**，
> 在控制台的「设置」页里生成，别搞混。

---

## 四、启动

```powershell
docker compose up -d
```

首次启动需要下载基础镜像，约 1-3 分钟（取决于网速）。

查看启动状态：

```powershell
docker compose ps
```

看到 `STATUS` 为 `Up (healthy)` 就成功了。

跟随日志（可选）：

```powershell
docker compose logs -f
```

看到这行就完全就绪：

```
[start] ===== ALL READY =====
```

---

## 五、打开控制台

浏览器访问：

```
http://127.0.0.1:3100
```

输入第 3 步设置的密钥登录。

首次登录会自动弹出 **5 步新手引导**，跟着点即可：

1. 确认代理节点
2. 添加账号
3. 拿 API Key
4. 接客户端

---

## 六、配置代理订阅

没有节点，所有 ChatGPT 请求都会失败。**这是必做步骤。**

1. 左侧「**代理设定**」
2. 在「更新订阅」输入框粘贴你的机场订阅链接
3. 点「更新订阅」
4. 等 10-30 秒，节点列表出现后，在顶部下拉框选一个 **美国** 或 **日本** 节点

验证：状态区应显示类似

```
出口 146.190.52.121 · US
```

地区显示为 `US` / `JP` 就说明代理正常。

> 节点是**纯手动**选择的，选完就锁定，不会自己跳。
> 重启容器后依然是你上次选的那个。

---

## 七、添加账号

1. 左侧「**号池管理**」
2. 右上角「**导入**」→「**OAuth 登录已有账号**」
3. 点「**打开授权页面**」
4. 会弹出一个内置浏览器窗口，在里面正常登录 ChatGPT
5. **登录成功后什么都不用做** —— 弹窗标题会变成「✅ 账号已自动添加」

> 如果 10 秒没反应，点弹窗右上角的「手动完成」。

---

## 八、拿 API Key

1. 左侧「**设置**」
2. 找到 **API Key**
3. 复制 `sk-` 开头的那一串

在 AI 客户端里填：

| 项 | 值 |
|---|---|
| Base URL | `http://127.0.0.1:3100/v1` |
| API Key | 刚才复制的 `sk-...` |

---

## 九、验证

```powershell
# 健康检查
curl http://127.0.0.1:3100/health

# 对话测试
curl http://127.0.0.1:3100/v1/chat/completions ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer sk-你的key" ^
  -d "{\"model\":\"auto\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}]}"
```

或者直接跑自检：

```powershell
python selfcheck.py
```

---

## 十、常用操作

```powershell
docker compose restart          # 重启
docker compose logs -f          # 看日志
docker compose down             # 停止
docker compose up -d --build    # 改代码后重建
```

### 开机自启

Docker Desktop 设置里：

**Settings → General → 勾选 "Start Docker Desktop when you sign in to your computer"**

容器本身已设置 `restart: unless-stopped`，Docker 起来后会自动拉起。

---

## 十一、常见问题

### 端口 3100 被占用

改 `docker-compose.yml`：

```yaml
ports:
  - "13100:3000"    # 改左边这个
```

然后 `docker compose up -d`，访问地址改成 `http://127.0.0.1:13100`。

查谁占用了端口：

```powershell
netstat -ano | findstr :3100
tasklist | findstr <上面查到的PID>
```

### 容器一直 restarts

```powershell
docker compose logs --tail 50
```

常见原因：
- `.env` 没建（`copy .env.example .env`）
- `mihomo-config.yaml` 格式坏了（重新拉一份模板）

### 打开页面显示 "无法访问"

```powershell
docker compose ps
```

如果 STATUS 不是 `Up`，说明没起来。看日志排查。

### 内置浏览器黑屏

Chromium 启动需要约 30-40 秒。如果一直黑：

```powershell
docker compose restart
```

### 想彻底重装

```powershell
docker compose down
# 注意：这会删掉 data/（账号、节点选择都在里面）
docker compose up -d
```

只清数据不删镜像：

```powershell
docker compose down
rmdir /s /q data
docker compose up -d
```

---

## 十二、下一步

- [Docker 通用部署说明](DEPLOY-DOCKER.md)
- [API 接口文档](API.md)
- [常见问题](FAQ.md)
- [架构说明](ARCHITECTURE.md)
