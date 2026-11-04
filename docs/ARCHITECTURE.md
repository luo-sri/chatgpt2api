# 架构与实现说明

面向想改代码、排查问题或做二次开发的读者。

---

## 一、整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                         宿主机（你的电脑/NAS）                     │
│                                                                  │
│   浏览器 ──────────┐                                             │
│   AI 客户端 ───────┼──▶ :3100 ─────────────────────────┐          │
│                    │                                  │          │
└────────────────────┼──────────────────────────────────┼──────────┘
                     │  Docker 端口映射                  │
┌────────────────────▼──────────────────────────────────▼──────────┐
│                      容器 chatgpt2api-allinone                    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  gateway.py  :3000   （对外唯一入口）                       │  │
│  │   ├─ /v1/*        OpenAI 兼容 API → 面板 3001              │  │
│  │   ├─ /p/chat     对话页（chat_page.py）                    │  │
│  │   ├─ /p/proxy    代理页（proxy_page.py）                   │  │
│  │   ├─ /p/oauth    添加账号引导页                            │  │
│  │   ├─ /p/api/*    管理接口 → webapi.py                      │  │
│  │   └─ /images/*   图片静态资源 → 面板                       │  │
│  └────────────────────────────────────────────────────────────┘  │
│           │                        │                    │         │
│           ▼                        ▼                    ▼         │
│  ┌────────────────┐   ┌────────────────────┐  ┌──────────────┐   │
│  │ 面板 :3001     │   │ mihomo :7890/:9090 │  │ Chromium     │   │
│  │ FastAPI        │   │ 代理内核            │  │ :9222 (CDP)  │   │
│  │ Next.js 前端   │   │ 出口 → OpenAI      │  │ + Xvfb       │   │
│  │ 账号池          │   └────────────────────┘  │ + x11vnc     │   │
│  └────────────────┘                            │ + noVNC:6080 │   │
│                                                 └──────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 二、进程启动顺序

`start.sh` 是容器入口，按顺序拉起 5 个服务：

| 顺序 | 服务 | 端口 | 作用 | 就绪判断 |
|---|---|---|---|---|
| 1 | mihomo | 7890 / 9090 | 代理内核 | 9090 可访问 |
| 2 | patch_webdist.py | — | 前端补丁（一次性） | 执行完即退出 |
| 3 | uvicorn 面板 | 3001 | 账号池 + 原生 UI | `/api/version` 可达 |
| 4 | gateway.py | 3000 | 网关 + 定制页面 | 3000 可访问 |
| 5 | browser.sh | 9222 / 6080 | Chromium + noVNC | 9222 可访问 |

任何一步失败，`start.sh` 会打印日志并退出，Docker 依据
`restart: unless-stopped` 自动重启。

---

## 三、请求链路

### 3.1 对话请求

```
客户端 POST /v1/chat/completions
  → gateway.py 校验 API Key（_client_key / _auth_ok）
  → 注入面板 Key（_with_key / _page_api_key）
  → 转发到 3001 /v1/chat/completions
  → 面板调 ChatGPT 网页接口（经 7890 代理）
  → 流式返回时过 StreamCleaner 净化
  → 以 SSE 吐给客户端
```

### 3.2 页面请求

```
浏览器 GET /p/chat
  → gateway.py 判断路径
  → 返回 webui.render_pages() 生成的 HTML
  → HTML 里注入 sk- Key（__C2A_KEY__ 占位替换）
  → 前端 fetch /v1/models 拿模型列表
```

### 3.3 原生面板页（号池/日志/设置等）

```
浏览器 GET /accounts
  → gateway.py 走 _proxy_to_panel()
  → 反向代理到 3001
  → HTML 里注入导航条（inject_navbar） + 新手引导
  → chunk 里的补丁已由 patch_webdist 打好
```

---

## 四、前端补丁机制（核心）

### 为什么需要补丁

原生面板是编译好的 Next.js 产物，改不了源码。但我们需要：

- 加菜单项（对话 / 代理设定）
- 去掉不需要的入口（无限画布）
- 改文案（额度 → 生图额度）
- 加按钮（清空日志）
- 改品牌（GitHub 链接、版本号）

**做法：启动时用 Python 直接改 chunk 文件**，改完写回，浏览器拿到新文件。
每次容器启动执行一次，幂等（重复执行不会叠加）。

### 关键文件

`patch_webdist.py`：

| 函数 | 作用 | 幂等标记 |
|---|---|---|
| `patch_nav()` | 替换导航数组 | `NAV_MARK` |
| `patch_oauth_open()` | 拦截 window.open → 内置浏览器 | `c2a-oauth-patched` |
| `remove_canvas()` | 删除「无限画布」入口 | `c2a-no-canvas` |
| `patch_brand()` | GitHub 链接 + 版本检查源 | `c2a-brand` |
| `patch_app_version()` | bundle 里的 appVersion 常量 | 值比对 |
| `inject_logs_button()` | 日志页加「清空全部日志」 | `c2a-del-failed` |
| `patch_quota_label()` | 额度 → 生图额度 | `c2a-quota-label` |
| `inject_models_toggle()` | 号池页「管理模型」浮层 | `c2a-msw-head` |
| `rename_patched_chunks()` | 生成 `-patched.js` 并改 HTML 引用 | — |

### 幂等性怎么保证

两层的做法：

1. **标记检测**：函数开头检查目标文件里是否已有标记，有就返回 `already`
2. **结构检测**：有些补丁（如 `inject_models_toggle`）同时检查 DOM 锚点
   和逻辑标记，避免「文本还在但结构已变」时重复插入

> 踩过的坑：早期用「结尾字符串匹配」判断，容器重启多次后补丁会叠加，
> 「管理模型」按钮最多出现了 5 个。现在的绝对幂等判断解决了这个问题。

### 为什么静态资源也要 no-store

Next.js chunk 名字是固定的（如 `0xaq6n.l11b6j.js`），不是带 hash 的。
浏览器会按启发式规则缓存，导致「改了代码但页面不变」。

所以网关对所有响应加：

```
Cache-Control: no-store, no-cache, must-revalidate, max-age=0
```

---

## 五、内置浏览器与 OAuth

### 组件关系

```
browser.sh
  ├─ Xvfb :99           虚拟屏幕（无显示器也能跑图形界面）
  ├─ Chromium           给 --remote-debugging-port=9222 开 CDP
  ├─ x11vnc :5900       把 X 画面转成 VNC
  └─ noVNC :6080        把 VNC 转成网页，浏览器里就能看
```

### 加账号流程

```
用户点「打开授权页面」
  → 前端调 POST /p/api/oauth/start 拿授权 URL
  → 前端调 POST /p/api/oauth/open
  → webapi.browser_open() → cdpeval.open_url()
  → CDP 让 Chromium 新开标签访问授权页
  → 前端弹出 noVNC 窗口（画面来自 6080）
  → 用户在窗口里登录
  → 浏览器跳转到 platform.openai.com/auth/callback?code=...
  → cdpeval 的常驻 Target 监听瞬间捕获该 URL（落盘）
  → 前端每 3 秒调 POST /p/api/oauth/auto
  → webapi.oauth_auto_finish() 读回调 → 调面板 finish → 入库
  → 成功后清空缓存、关掉回调标签
```

### 三个关键设计

**1. 为什么用 Target 事件监听而不是轮询**

授权回调页加载后会**立刻重定向**，3 秒一次的轮询几乎必然错过。
`cdpeval.start_monitor()` 订阅浏览器级 `Target` 事件，任何导航都能立刻捕获。

**2. 为什么不是复制粘贴**

内置浏览器的画面通过 VNC 投射到宿主机浏览器，**剪贴板不互通**。
用户在窗口里复制的文字，宿主机拿不到。所以必须由服务端代劳。

**3. 为什么成功后要清缓存**

`code` 是一次性的。如果留着，下次打开授权窗口会把这条旧 code 填进去，
必然报「state 不匹配」，用户会以为功能坏了。

### 禁用 IPv6 的原因

Chromium 默认 IPv6 优先，但 mihomo 只提供 IPv4 出口。
不加 `--disable-ipv6`，部分请求会绕过代理直连，导致：

- 出口 IP 显示成本机宽带地址
- 地区显示错误（比如显示 GB 而节点是美国）
- ChatGPT 可能因为 IP 不一致而拒绝

---

## 六、流式输出净化

### 问题

ChatGPT 网页接口返回的内容里，可能混入内部的 JSX/GenUI 标记，例如：

```
<AsyncImage src="..." />
{@body const x = 1}
```

直接吐给用户，看起来像「回复里夹着项目代码」。

### 解法

`stream_clean.py` 的 `StreamCleaner`：

```python
sc = StreamCleaner()
for chunk in upstream:
    clean = sc.feed(chunk)   # 跨 chunk 安全
yield sc.flush()
```

要点：

- **跨 chunk 缓冲**：一个标签可能被切成两个 chunk（`<Async` + `Image .../>`），
  遇到未闭合的 `<` 或 `{@` 先扣住，等后续数据
- **上限保护**：`MAX_HOLD = 4000`，超过就放弃缓冲直接输出，防卡死
- **代码块内不清洗**：用户主动让 AI 写代码时，代码里的 `<div>` 不能删

非流式响应用 `jsx_clean.py` 的 `strip_jsx()`，逻辑相同但不需缓冲。

---

## 七、代理管理

### 分组结构

```
ChatGPT（Selector）
  → 节点选择（Selector）
    → 具体节点（ss / vmess / trojan ...）
```

页面**只读「节点选择」组的 now 作为当前节点**。
订阅自带的「自动选择」（URLTest 组）在页面上不显示、也不参与选择。

### 纯手动的实现

```python
def select_node(node):
    jput(MIHOMO + "/proxies/节点选择", {"name": node})   # 切分组
    jput(MIHOMO + "/proxies/ChatGPT", {"name": "节点选择"})  # 确保链路
    open("/app/data/selected-node.txt", "w").write(node)   # 落盘
    # 清空出口/延迟缓存，触发重新探测
```

容器启动 12 秒后，`apply_saved_node()` 读取 `selected-node.txt` 并套用，
所以重启后不会漂移。

### 出口 IP 探测

```python
def _exit_probe():
    # 首选 Cloudflare trace（和 ChatGPT 实际出口同路径）
    # 只接受 IPv4：拿到 IPv6 说明没走代理，丢弃
    # 兜底：api4.ipify.org + ip-api
```

结果缓存 25 秒，页面请求只读缓存（不阻塞），探测在后台线程做。
这让代理页刷新从 6.7 秒降到 0.02 秒。

---

## 八、双 Key 体系

这是最容易混淆的地方：

| Key | 存在哪 | 用途 | 长什么样 |
|---|---|---|---|
| `CHATGPT2API_AUTH_KEY` | `.env` | 登录控制台 | `my-secret-2026` 这种普通字符串 |
| API Key | `data/auth_keys.json` | 调 `/v1/*` 接口 | `sk-` 开头 |

网关的 `_auth_ok()` 对两者都放行（面板自己的鉴权也接受登录口令），
但**第三方客户端必须用 `sk-` 那个**。

页面里的 `sk-` 存在 `data/page-api-key.txt`，通过 `_with_key()`
注入到 HTML 的 `__C2A_KEY__` 占位处。

---

## 九、数据文件

| 文件 | 内容 | 删了会怎样 |
|---|---|---|
| `data/accounts.json` | 账号池（含 token） | 账号全丢，要重新登录 |
| `data/auth_keys.json` | API Key 列表 | 客户端全部 401 |
| `data/page-api-key.txt` | 页面用的 sk- key | 页面调不通接口 |
| `data/selected-node.txt` | 用户选的节点 | 回默认美国-03 |
| `data/model-off.json` | 禁用模型清单 | 全部模型重新出现 |
| `data/removed-nodes.json` | 已删节点 | 删过的节点回来 |
| `data/oauth-callback.json` | 最近抓到的回调 | 无影响（临时的） |
| `data/chrome-profile/` | 浏览器登录态 | 要重新登录 |
| `data/logs.jsonl` | 调用日志 | 无影响 |

---

## 十、二次开发

### 改代码后怎么生效

| 改了什么 | 生效方式 |
|---|---|
| `.py`（页面/逻辑） | `docker cp 文件 容器:/opt/gateway/` → `docker restart` |
| `Dockerfile` / `.sh` | `docker compose up -d --build` |
| 补丁目标 chunk | 改 `patch_webdist.py` 后重建 |

**长期改动必须重建镜像**，否则容器重建后丢失。

### 加一个新的补丁

1. 在 `patch_webdist.py` 加函数
2. 函数开头做幂等判断（检查标记）
3. 在 `patch_all()` 的 results 字典里注册
4. 重建 → 看日志确认 `[patch:xxx] ok`

### 改补丁可能踩的坑

| 坑 | 表现 | 解法 |
|---|---|---|
| 锚点失效 | `[patch:xxx] fail -> 锚点未命中` | 面板版本变了，重新找锚点 |
| 幂等失效 | 按钮越重启越多 | 用标记 + 结构双重判断 |
| `</script>` 提前闭合 | 页面 JS 报 `Invalid or unexpected token` | 字符串里不能有 `</script>`，`\n` 要用 `String.fromCharCode(10)` |
| CRLF | `.sh` 报 `set: Illegal option -` | Windows 编辑后转 LF |

### 验证

```bash
python selfcheck.py
```

覆盖 61 项，改完必跑。

---

## 十一、自检脚本

`selfcheck.py` 分 9 组：

| 组 | 检查内容 |
|---|---|
| 一、服务健康 | `/health`、容器状态、端口映射 |
| 二、页面路由 | 10 个页面是否都 200 |
| 三、API 与认证 | 三种认证方式、无效 Key 拒绝、模型列表 |
| 四、代理与节点 | 分组结构、出口 IP/地区、节点列表、持久化 |
| 五、账号池 | 账号数、状态、额度 |
| 六、OAuth 链路 | 回调缓存状态、调试端口、IPv6 禁用 |
| 七、模型开关 | 禁用清单可读、接口正常 |
| 八、文件完整性 | 20 个核心文件是否存在 |
| 九、CRLF | 4 个 .sh 是否 LF |

退出码 0 = 全过，1 = 有失败。
