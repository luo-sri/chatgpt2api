# -*- coding: utf-8 -*-
"""流式 JSX/UI 标签清洗器

问题背景：
  ChatGPT 网页版会输出 React/GenUI 组件（<AsyncImage .../>、{@body ...} 等）。
  非流式时可以对整段文本做正则清洗；但流式是把回复切成任意片段的 chunk，
  一个标签可能被拆成 "<AsyncI" + "mage src=..." + "/>" 三段。
  如果逐片直接推送，客户端就会看到残缺的代码/标签 —— 这正是
  "API 回复里混着项目代码" 的根因。

方案：
  增量清洗器 _buf：暂存可能未闭合的标签片段，只在确认安全时才输出。
    · 遇到 '<' 且后面还没出现 '>' → 先把 '<' 之前的内容推送，'<' 起的内容留在缓冲
    · 遇到 '{@' → 同上（JSX 表达式块）
    · 缓冲长度超过 MAX_HOLD 仍无闭合 → 认为不是标签，原样放出（防止卡死）
  flush() 在流结束时把残余按最后清洗规则处理。
"""
import re

# 单标签整块丢弃（这些是纯 UI 元素，正文里没有价值）
_DROP_SINGLE = (
    "<badge>", "</badge>", "<escape>", "</escape>", "<box>", "</box>",
)
# 整段丢弃（含内容）
_DROP_BLOCK_RE = re.compile(
    r"<\s*(?:AsyncImage|AsyncImageGroup|Image|ImageGroup|Img|Video|Audio|"
    r"iframe|MapEmbed|Map|SearchResult|Source|Cite|Entity|Chart|CodeBlock|Table)\b"
    r"[^>]*?(?:/>|>[\s\S]*?</\s*(?:AsyncImage|AsyncImageGroup|Image|ImageGroup|Img|"
    r"Video|Audio|iframe|MapEmbed|Map|SearchResult|Source|Cite|Entity|Chart|CodeBlock|Table)\s*>)",
    re.I)
# 自闭合 / 普通标签
_SELF_RE = re.compile(r"<\s*[A-Za-z][A-Za-z0-9_.-]*\b[^<>]*?/>")
_PAIR_RE = re.compile(r"<\s*([A-Za-z][A-Za-z0-9_.-]*)\b[^<>]*?>[\s\S]*?</\s*\1\s*>")
# {@body ...} 整行
_BODY_LINE_RE = re.compile(r"\{@(?:body|code|expr)\b[^\n]*\}", re.I)

MAX_HOLD = 4000   # 缓冲上限，超过就当作普通文本放出


class StreamCleaner:
    """增量清洗：喂进 chunk，取出可安全输出的文本。"""

    def __init__(self):
        self.buf = ""
        self.in_code = False     # 是否处在 ``` 代码块中（代码块内不清洗）
        self.emitted = 0

    # ---------- 内部：对一段“确定完整”的文本做清洗 ----------
    @staticmethod
    def _clean(text):
        if not text:
            return ""
        # 代码块保护：只清洗代码块之外的文本
        parts = re.split(r"(```[\s\S]*?```)", text)
        out = []
        for i, seg in enumerate(parts):
            if i % 2 == 1:          # 代码块原样保留
                out.append(seg)
                continue
            s = seg
            for t in _DROP_SINGLE:
                s = s.replace(t, "")
            prev = None
            while prev != s:
                prev = s
                s = _DROP_BLOCK_RE.sub("", s)
                s = _SELF_RE.sub("", s)
                s = _PAIR_RE.sub("", s)
            s = _BODY_LINE_RE.sub("", s)
            out.append(s)
        text = "".join(out)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def feed(self, chunk):
        """喂入一个 chunk，返回可以安全推送的文本（可能为空串）。"""
        if not chunk:
            return ""
        self.buf += chunk
        out = ""

        while True:
            # 找最近的“可能未闭合”起点：'<' 或 '{@'
            lt = self.buf.rfind("<")
            at = self.buf.rfind("{@")
            cut = max(lt, at)

            if cut < 0:
                # 没有可疑起点 → 全部可安全输出
                piece = self.buf
                self.buf = ""
                out += self._safe(piece)
                break

            # 判断该起点之后是否已经闭合
            tail = self.buf[cut:]
            closed = (">" in tail) if cut == lt else ("}" in tail)

            if closed:
                # 已闭合 → 连同标签一起处理，但不是整段输出：
                # 把 cut 之前的立即输出，剩下的继续留在 buf 里等下一次
                piece = self.buf[:cut]
                self.buf = self.buf[cut:]
                if piece:
                    out += self._safe(piece)
                # 缓冲里已经有闭合标签，可以直接整体清洗并输出
                # （再往后可能还有未闭合的，所以循环继续）
                # 为避免无限循环，把已闭合部分先取出来
                # 找到最后一个 '>' 的位置作为安全边界
                last_gt = self.buf.rfind(">")
                if last_gt >= 0:
                    safe = self.buf[:last_gt + 1]
                    self.buf = self.buf[last_gt + 1:]
                    out += self._safe(safe)
                    continue
                break
            else:
                # 未闭合：先输出前面安全部分，剩余留在缓冲
                piece = self.buf[:cut]
                self.buf = self.buf[cut:]
                if piece:
                    out += self._safe(piece)
                # 缓冲过长 → 判定不是标签，原样放出
                if len(self.buf) > MAX_HOLD:
                    out += self.buf
                    self.buf = ""
                break

        self.emitted += len(out)
        return out

    def _safe(self, piece):
        """清洗一段确定安全的文本（代码块内不清洗）。"""
        if not piece:
            return ""
        # 处理 ``` 开关，跨 chunk 时也要正确
        res = []
        i = 0
        while i < len(piece):
            if piece.startswith("```", i):
                self.in_code = not self.in_code
                res.append("```")
                i += 3
                continue
            j = piece.find("```", i)
            if j < 0:
                seg = piece[i:]
                res.append(seg if self.in_code else self._clean(seg))
                break
            seg = piece[i:j]
            res.append(seg if self.in_code else self._clean(seg))
            i = j
        return "".join(res)

    def flush(self):
        """流结束：把残余缓冲清理后输出。"""
        if not self.buf:
            return ""
        rest = self.buf
        self.buf = ""
        # 结束还不闭合的标签 → 直接丢弃（它一定是残缺 UI 组件）
        if rest.startswith("<") and ">" not in rest:
            return ""
        if rest.startswith("{@") and "}" not in rest:
            return ""
        return self._clean(rest)
