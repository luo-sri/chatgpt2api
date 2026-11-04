# API 接口文档

本项目提供 OpenAI 兼容接口，任何支持 OpenAI 协议的客户端/库都能直接用。

---

## 一、基本信息

| 项 | 值 |
|---|---|
| Base URL | `http://<主机>:3100/v1` |
| 认证 | `sk-` 开头的 API Key（在「设置」页获取） |
| 响应格式 | JSON（流式为 SSE） |
| 兼容性 | OpenAI Chat Completions / Images / Anthropic Messages |

---

## 二、认证方式

三种任选其一：

### 1. Authorization 头（最常用）

```bash
curl http://127.0.0.1:3100/v1/models \
  -H "Authorization: Bearer sk-你的key"
```

### 2. x-api-key 头

```bash
curl http://127.0.0.1:3100/v1/models \
  -H "x-api-key: sk-你的key"
```

### 3. 查询参数

```bash
curl "http://127.0.0.1:3100/v1/models?api_key=sk-你的key"
```

### 错误响应

Key 无效时返回 `401`：

```json
{"error": {"message": "invalid api key", "type": "unauthorized"}}
```

> ⚠️ 注意区分两个密钥：
> - `CHATGPT2API_AUTH_KEY`（在 `.env` 里）= 登录控制台用
> - `sk-...`（在「设置」页）= 调 API 用

---

## 三、对话接口

### `POST /v1/chat/completions`

#### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `model` | string | 是 | `auto` / `gpt-6` / `gpt-5-6` 等 |
| `messages` | array | 是 | 消息列表 |
| `stream` | bool | 否 | 是否流式，默认 `false` |
| `temperature` | number | 否 | 0-2，默认 1 |
| `max_tokens` | int | 否 | 最大输出长度 |
| `tools` | array | 否 | 工具定义（函数调用） |
| `tool_choice` | string | 否 | `auto` / `none` |

#### 非流式示例

```bash
curl http://127.0.0.1:3100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-你的key" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "用一句话介绍你自己"}],
    "stream": false
  }'
```

响应：

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1793789114,
  "model": "auto",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "我是 ChatGPT，一个 AI 助手。"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 12, "completion_tokens": 15, "total_tokens": 27}
}
```

#### 流式示例

```bash
curl http://127.0.0.1:3100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-你的key" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "数到 5"}],
    "stream": true
  }'
```

响应（SSE）：

```
data: {"choices":[{"delta":{"content":"1"}}]}
data: {"choices":[{"delta":{"content":"、"}}]}
data: {"choices":[{"delta":{"content":"2"}}]}
...
data: [DONE]
```

#### 工具调用

```bash
curl http://127.0.0.1:3100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-你的key" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "北京今天天气怎么样"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "查询指定城市的天气",
        "parameters": {
          "type": "object",
          "properties": {"city": {"type": "string"}},
          "required": ["city"]
        }
      }
    }]
  }'
```

---

## 四、模型接口

### `GET /v1/models`

```bash
curl http://127.0.0.1:3100/v1/models \
  -H "Authorization: Bearer sk-你的key"
```

响应：

```json
{
  "object": "list",
  "data": [
    {"id": "auto", "object": "model", "created": 0, "owned_by": "system"},
    {"id": "gpt-6", "object": "model", "created": 0, "owned_by": "system"},
    {"id": "gpt-image-2", "object": "model", "created": 0, "owned_by": "system"}
  ]
}
```

> 列表里只会出现**已启用**的模型。在「号池管理 → 管理模型」里可以逐个开关，
> 禁用的模型不会出现在列表中，也无法调用。

---

## 五、生图接口

### `POST /v1/images/generations`

#### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `model` | string | 是 | `gpt-image-2` |
| `prompt` | string | 是 | 图片描述 |
| `n` | int | 否 | 生成数量，默认 1 |
| `size` | string | 否 | `1024x1024` / `1536x1024` / `1024x1536` |
| `image_url` | string | 否 | 图生图时的参考图地址 |

#### 文生图

```bash
curl http://127.0.0.1:3100/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-你的key" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "一只戴墨镜的橘猫，写实风格",
    "n": 1,
    "size": "1024x1024"
  }'
```

响应：

```json
{
  "created": 1793789114,
  "data": [{
    "url": "http://127.0.0.1:3100/images/2026/11/04/abc123.png"
  }]
}
```

> 返回的 URL 会自动改写成**你当前访问的地址**（3100 端口），
> 直接用浏览器打开就能看图，不需要额外配置。

#### 图生图

```bash
curl http://127.0.0.1:3100/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-你的key" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "把这只猫画成卡通风格",
    "image_url": "https://example.com/cat.jpg",
    "n": 1
  }'
```

---

## 六、Python SDK

完全兼容官方 `openai` 库：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:3100/v1",
    api_key="sk-你的key",
)

# 对话
r = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "你好"}],
)
print(r.choices[0].message.content)

# 流式
for chunk in client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "写首诗"}],
    stream=True,
):
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)

# 生图
img = client.images.generate(
    model="gpt-image-2",
    prompt="赛博朋克风格的城市夜景",
    size="1024x1024",
)
print(img.data[0].url)

# 工具调用
import json
tools = [{
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "获取当前时间",
        "parameters": {"type": "object", "properties": {}},
    },
}]
r = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "现在几点"}],
    tools=tools,
)
if r.choices[0].message.tool_calls:
    print(r.choices[0].message.tool_calls[0].function)
```

---

## 七、常见客户端配置

### Cherry Studio

1. 设置 → 模型服务 → 添加 → 类型选 **OpenAI**
2. API 地址：`http://127.0.0.1:3100/v1`
3. API 密钥：`sk-...`
4. 模型：点「获取模型列表」或手动加 `auto`

### ChatBox

1. 设置 → 模型 → **OpenAI API**
2. API 域名：`http://127.0.0.1:3100`
3. API 密钥：`sk-...`
4. 模型：`auto`

### Cline（VSCode 插件）

1. 选 **OpenAI Compatible**
2. Base URL：`http://127.0.0.1:3100/v1`
3. API Key：`sk-...`
4. Model ID：`auto`

### Dify

1. 设置 → 模型供应商 → **OpenAI-API-compatible**
2. API endpoint：`http://127.0.0.1:3100/v1`
3. API Key：`sk-...`
4. 模型名称：`auto`

### OpenAI 官方 SDK（任意语言）

```python
# Python
OpenAI(base_url="http://127.0.0.1:3100/v1", api_key="sk-...")

# Node.js
new OpenAI({ baseURL: "http://127.0.0.1:3100/v1", apiKey: "sk-..." })
```

---

## 八、错误码

| HTTP | 含义 | 常见原因 |
|---|---|---|
| 401 | 未授权 | Key 错误 / 没传 Key |
| 404 | 路径错误 | Base URL 少写 `/v1` |
| 429 | 限流 | 账号额度用完 |
| 500 | 服务端错误 | 上游异常，重试 |
| 502 | 上游错误 | 节点不可用 / 账号被限流 |

错误响应格式：

```json
{
  "error": {
    "message": "具体错误信息",
    "type": "error_type"
  }
}
```

常见错误信息与处理：

| 错误 | 意思 | 怎么办 |
|---|---|---|
| `model not available to any active account` | 没有可用账号 | 加账号 / 等额度重置 |
| `no available image quota` | 生图额度用完 | 等次日重置（约 11:57） |
| `upstream timeout` | 上游超时 | 换节点重试 |

---

## 九、限流与配额

| 项目 | 免费账号额度 | 重置周期 |
|---|---|---|
| 生图 | 5 张 | 每天 |
| 推理/思考 | 约 120 次 | 每天 |
| 深度研究 | 5 次 | 每月 |

额度用完后账号状态变「限流」，该账号所有模型不可用。
号池里如果有多个账号，会自动切换。

---

## 十、内部管理接口

页面用的接口（需要登录态，一般不需要手工调）：

| 路径 | 方法 | 说明 |
|---|---|---|
| `/p/api/proxy` | GET | 分组、节点、延迟、出口 IP |
| `/p/api/proxy/select` | POST | 切节点，body `{"node":"节点名"}` |
| `/p/api/proxy/remove-node` | POST | 删/恢复节点，`{"node":..,"undo":bool}` |
| `/p/api/accounts` | GET | 账号数与列表 |
| `/p/api/models/off` | GET/POST | 模型禁用清单 |
| `/p/api/logs/clear` | POST | 清空全部日志 |
| `/p/api/oauth/auto` | POST | 自动完成账号添加 |
| `/health` | GET | 健康检查 |

完整清单见 [ARCHITECTURE.md](ARCHITECTURE.md)。
