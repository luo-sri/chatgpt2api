# -*- coding: utf-8 -*-
"""JSX / GenUI 清洗器

ChatGPT 网页版会在回复里输出 React 组件（GenUI），纯文本客户端会把它当正文显示。
不能用正则处理，因为属性里含 => 、引号内可能含 > 、还有 {@body ...} 表达式块。

做法：状态机逐字符扫描，正确处理
  1. {@body ... } 等 JSX 表达式行（整行删除）
  2. 标签属性里的引号（" ' `）
  3. 属性里的花括号（{...}，可能嵌套）
  4. onClick={() => ...} 中的 =>
  5. 自闭合 <X />
  6. 代码块保护（``` 和 `code` 不参与清洗）
"""
import re

# 需要整块删除的组件（图片/卡片类，无正文价值）
DROP_WHOLE = {
    "AsyncImage", "AsyncImageGroup", "Image", "ImageGroup", "Img",
    "Video", "Audio", "iframe", "MapEmbed", "Map",
    "SearchResult", "Reference", "Source", "Cite", "Entity",
    "Chart", "CodeBlock", "Table",
}

# JSX 表达式行：整行删除（例如 {@body const [x,setX] = DIL.useState(...)}）
BODY_LINE_RE = re.compile(r"^\s*\{@(?:body|code|expr)\b.*$", re.M)
# 单独的 JSX 表达式（如 {topic}、GenUI.xxx()）
INLINE_EXPR_RE = re.compile(r"\{[^{}\n]{0,200}\}")


def _protect_code(text):
    """把代码块抽出来，避免被误清洗"""
    store = []

    def keep(m):
        store.append(m.group(0))
        return f"\x00CODE{len(store)-1}\x00"

    text = re.sub(r"```[\s\S]*?```", keep, text)
    text = re.sub(r"`[^`\n]+`", keep, text)
    return text, store


def _restore_code(text, store):
    for i, s in enumerate(store):
        text = text.replace(f"\x00CODE{i}\x00", s)
    return text


def _is_tag_start(text, i):
    """判断 < 是否开启一个标签（而不是 < 3 这类比较）"""
    m = re.match(r"</?([A-Za-z][\w.:-]*)", text[i:])
    if not m:
        return None
    return m.group(1)


def _skip_tag(text, i, n):
    """从 < 开始，返回标签结束后的位置。正确跳过引号与花括号内的 >"""
    j = i + 1
    quote = None
    brace = 0
    while j < n:
        ch = text[j]
        if quote:
            if ch == quote and text[j - 1] != "\\":
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch == "{":
            brace += 1
        elif ch == "}":
            if brace > 0:
                brace -= 1
        elif ch == ">" and brace == 0:
            return j + 1
        j += 1
    return n  # 未闭合，吞到结尾


def strip_jsx(text):
    """删除 JSX 标签（保留标签内文字），并删除 JSX 表达式"""
    if not text:
        return ""

    text, code_store = _protect_code(text)

    # 1) 删除 {@body ...} 这类表达式行
    text = BODY_LINE_RE.sub("", text)

    # 2) 状态机扫描标签
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "<":
            name = _is_tag_start(text, i)
            if name:
                closing = text.startswith("</", i)
                end = _skip_tag(text, i, n)
                # 整块删除的组件：连内容一起吞掉
                if name in DROP_WHOLE and not closing:
                    close = text.find(f"</{name}", end)
                    if close >= 0:
                        end = _skip_tag(text, close, n)
                i = end
                continue
        out.append(ch)
        i += 1
    text = "".join(out)

    # 3) 删除残留的 JSX 表达式 {topic} 之类
    text = INLINE_EXPR_RE.sub("", text)

    # 4) 收拾空行与悬挂缩进
    lines = [ln.rstrip() for ln in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    text = _restore_code(text, code_store)
    return text.strip()


# ---------------------------------------------------------------- 自测
if __name__ == "__main__":
    sample = '''我认为算力布局最值得关注。

{@body const [topic,setTopic] = DIL.useState("OpenAI 内部动态与 Sam Altman 的最新消息")}
<box border radius="lg" padding={3} gap={3}>
你今晚最想了解哪方面?
<radio-group direction="col" value={topic} onChange={setTopic}>
<radio value="A">Sam Altman 和 OpenAI 内部动态</radio>
<radio value="B">GPT-6 系列模型最新进展</radio>
</radio-group>
<divider color="subtle"/>
希望了解的深度
<radio-group direction="col" value={depth} onChange={setDepth}>
<radio value="简明">简明新闻速报</radio>
</radio-group>
<button block onClick={()=>GenUI.issueNewTurn("请详细介绍: "+topic)}>开始深入了解</button>
</box>

今晚我们可以好好梳理一遍。'''
    print(strip_jsx(sample))
