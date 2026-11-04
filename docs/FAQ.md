# 常见问题（FAQ）

按症状查。每条都给出「为什么」和「怎么办」。

---

## 启动与访问

### 打不开 http://127.0.0.1:3100

**按顺序查：**

1. 容器起来了吗？

```bash
docker compose ps
```

要看到 `Up (healthy)` 或至少 `Up`。

2. 起不来就看日志：

```bash
docker compose logs --tail 50
```

3. 日志里有 `[start] ===== ALL READY =====` 吗？

没有的话，看它卡在哪一步（mihomo / 面板 / 网关 / 浏览器）。

4. 端口映射对吗？

```bash
docker port chatgpt2api-allinone
```

应该能看到 `3000/tcp -> 0.0.0.0:3100`。

5. 端口被占用？

```bash
# Windows
netstat -ano | findstr :3100

# Linux / macOS
lsof -i :3100
```

被占用就改 `docker-compose.yml` 里的宿主机端口。

---

### 容器一直重启（restarting）

```bash
docker compose logs --tail 100
```

常见原因：

| 日志特征 | 原因 | 解决 |
|---|---|---|
| `set: Illegal option -` | `.sh` 文件是 CRLF 换行 | 转成 LF（见下） |
| `mihomo` 报 YAML 错误 | `mihomo-config.yaml` 格式坏了 | 重新拉模板 |
| `No such file .env` | 没建 `.env` | `cp .env.example .env` |
| `Permission denied` | data 目录权限不对 | `chown -R 1000:1000 data/` |

**CRLF 转 LF**（Windows 编辑过 .sh 就会这样）：

```bash
# Git Bash / WSL
sed -i 's/\r$//' start.sh browser.sh backup.sh

# 或 Python
python -c "import glob; [open(f,'wb').write(open(f,'rb').read().replace(b'\r\n',b'\n')) for f in glob.glob('*.sh')]"
```

---

### 页面能开，但一直跳回登录页

密钥不对。

用 `.env` 里的 `CHATGPT2API_AUTH_KEY`：

```bash
cat .env
```

改了 `.env` 后需要重建容器才生效：

```bash
docker compose up -d
```

---

## 账号相关

### 加账号时弹窗是空白的

**原因**：6080 端口没映射，或内置浏览器没起来。

**检查：**

```bash
docker port chatgpt2api-allinone | grep 6080
```

没输出就是没映射，在 `docker-compose.yml` 里加：

```yaml
ports:
  - "6080:6080"
```

然后重建。

如果端口有映射但页面还是空白，等 40 秒（Chromium 启动慢），或：

```bash
docker compose restart
```

---

### 加账号登录完没自动完成

**原因**：可能登录流程没走完，或回调页被跳过。

**怎么办**：点弹窗右上角的「**手动完成**」，它会再等 8 秒抓一次。

还不行就检查：

```bash
# 看浏览器现在停在哪个页面
curl http://127.0.0.1:3100/p/api/browser/tabs
```

如果 URL 里有 `platform.openai.com/auth/callback?code=...`，说明回调在，
点「手动完成」应该能成功。

---

### 提示「state 不匹配」

**原因**：`code` 是**一次性**的，重复使用必然报这个。

常见场景：

1. 你点过两次「打开授权页面」，登录的是前一次开的窗口
2. 上一次的账号其实已经加成功了，但你又点了一次

**解决**：回号池管理，点「重新生成」，重新登录一次。

---

### 账号显示「限流」

**原因**：额度用完了。

| 项目 | 免费额度 | 重置时间 |
|---|---|---|
| 生图 | 5 张/天 | 次日约 11:57 |
| 推理/思考 | 约 120 次/天 | 次日 |

**解决**：

1. 等次日重置
2. 加更多账号进池（会自动轮换）
3. 升级 Plus

重置后在号池页点「**一键刷新所有账号信息和额度**」更新状态。

---

### 账号加进去了，但对话还是失败

按顺序查：

1. 节点可用吗？「代理设定」看出口 IP 和地区
2. 账号状态是「正常」吗？「号池管理」看
3. 模型被禁用了吗？「号池管理 → 管理模型」看
4. 额度还有吗？

测试命令：

```bash
curl http://127.0.0.1:3100/v1/models -H "Authorization: Bearer sk-你的key"
```

返回空列表或很少的模型，说明账号有问题。

---

## 对话相关

### API 报 401

**原因**：Key 用错了。

两个 Key 要分清：

| Key | 从哪拿 | 用在哪 |
|---|---|---|
| 登录密码 | `.env` 里的 `CHATGPT2API_AUTH_KEY` | 登录控制台 |
| API Key | 「设置」页的 `sk-...` | 调 `/v1/*` 接口 |

客户端里要填的是 **`sk-` 开头**的那个。

---

### 模型列表很少 / 只有几个

**原因**（按可能性排序）：

1. **账号限流** → 看号池状态
2. **手动禁用了模型** → 「号池管理 → 管理模型」里看哪些被关了
3. **节点被拦** → 换节点重试

账号恢复额度后，点「一键刷新所有账号信息和额度」，
再刷新页面就能看到全部模型。

---

### 对话很慢（30 秒以上）

**原因**：ChatGPT 网页接口本身慢，尤其免费账号高峰期。

这属于正常现象，网关有 180 秒超时兜底。如果经常超过 60 秒，
建议：

- 换延迟更低的节点（「代理设定」里看延迟数字）
- 避开高峰期

---

### 回复里夹着代码 / 奇怪的标签

**原因**：上游返回了内部标记，净化没覆盖到。

本项目已有 `StreamCleaner` 处理常见的 JSX 和 GenUI 标记。
如果还遇到，请提 Issue 并贴出原始内容。

---

### 对话中途断了

**原因**：

1. 如果用了 Nginx 反代 → 关掉缓冲、加大超时（见 [Linux 部署](DEPLOY-LINUX.md)）
2. 上游超时 → 重试
3. 节点不稳 → 换节点

---

## 代理相关

### 节点列表是空的

**原因**：没配订阅，或订阅解析失败。

1. 「代理设定」→ 粘贴机场订阅链接
2. 点「更新订阅」
3. 等 10-30 秒

如果提示失败：

- 检查链接是否还有效（在浏览器里打开试试）
- 检查 NAS/服务器能否访问机场域名

---

### 节点全部显示红色 / 超时

**原因**：节点 IP 被墙、或机场线路故障。

**解决**：

1. 「代理设定」→ 「更新订阅」重新拉一次
2. 换其他地区的节点
3. 联系机场

---

### 出口 IP 显示的地区不对

**原因**：之前用 IPv6 探测会误判（已修复）。

现在强制走 IPv4，用 Cloudflare trace 探测（和 ChatGPT 看到的出口一致）。

如果还不对：

1. 点「全部测速」刷新
2. 或重启容器

---

### 换了节点但 IP 没变

**原因**：缓存（25 秒）。

等半分钟，或切到别的节点再切回来。

---

### 「自动选择」组是什么？会影响我的选择吗

**不影响。**

订阅里自带的 `自动选择`（URLTest 组）是机场配置的一部分，
本项目的页面**不显示它、也不使用它**。

你的节点是**纯手动**选的，选完就锁定，重启也保持。

---

## 生图相关

### 报 `no available image quota`

**原因**：生图额度用完了。

免费账号每天 5 张，次日约 11:57 重置。

**查看剩余**：「号池管理」→「生图额度」列。

---

### 图片返回的 URL 打不开

本项目已自动把上游返回的内部地址（`127.0.0.1:3001`）改写成
你访问时的地址（`3100`）。

如果还是打不开：

1. 确认用的是最新版本（`git pull` + 重建）
2. 如果是通过域名/反代访问，确认域名能解析到本机

---

## 日志与数据

### 日志太多，怎么清

「日志管理」→「**清空全部日志**」（红色按钮，会二次确认）。

这会清空面板日志 + 网关日志文件。

只想删失败的：「删除所有失败」。

---

### 数据备份怎么做

```bash
tar -czf backup-$(date +%F).tar.gz data/
```

`data/` 包含：账号、API Key、节点选择、模型开关、浏览器登录态。

恢复：

```bash
tar -xzf backup-2026-01-01.tar.gz
docker compose restart
```

---

### 迁移到另一台机器

1. 整个项目目录拷过去（含 `data/`）
2. `docker compose up -d --build`

账号、配置、Key 全都跟着走，不用重新配。

---

## 性能与资源

### 内存占用高

内置浏览器（Chromium + Xvfb）比较吃内存：

| 场景 | 内存 |
|---|---|
| 只用 API | 约 600 MB |
| 开过内置浏览器 | 1.5-2 GB |
| 多账号长期挂 | 2-4 GB |

不加账号时可以关掉浏览器部分省内存（改 `start.sh` 注释掉 `browser.sh`），
但那样就没法 OAuth 加账号了。

---

### 磁盘占用增长

```bash
docker system df
```

清理：

```bash
docker image prune -f          # 无用镜像
docker builder prune -f        # 构建缓存
```

日志限制（`docker-compose.yml`）：

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

---

## 安全

### 能暴露到公网吗

可以，但**必须**：

1. 改掉默认密钥（强密码）
2. 前面加 HTTPS 反代
3. 不要暴露 6080（内置浏览器画面）
4. 考虑加 IP 白名单

**不建议**直接把 3100 裸奔在公网。

---

### 内置浏览器会不会泄露我的账号

浏览器档案在 `data/chrome-profile/`，只有容器内部能访问。
但如果有人拿到了你的宿主机文件系统，就能拿到里面的 Cookie。

所以：

- 不要把 `data/` 提交到 Git（`.gitignore` 已排除）
- 分享项目时不要带 `data/`
- 本项目提供了 `cleanup_for_publish.py` 一键清除个人数据

---

## 其它

### 怎么检查一切是否正常

```bash
python selfcheck.py
```

61 项全过就没问题。

---

### 怎么升级到新版本

```bash
git pull
docker compose up -d --build
```

`data/` 会保留。

---

### 想看更详细的技术说明

- [架构与实现](ARCHITECTURE.md)
- [API 文档](API.md)
- [Docker 部署](DEPLOY-DOCKER.md)

---

### 提 Issue 时请附上

1. 操作系统 + Docker 版本
2. `docker compose ps` 输出
3. `docker compose logs --tail 100` 输出
4. `python selfcheck.py` 结果
5. 复现步骤

**贴日志前请把 `sk-` 开头的 Key、邮箱、token 打码。**
