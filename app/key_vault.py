# -*- coding: utf-8 -*-
"""用户密钥明文档案（网关侧）

背景：
  面板的 auth_keys.json 只存 key_hash（SHA256），创建后明文就被丢弃，
  列表接口永远拿不到明文。用户想再复制一次密钥就只能删了重建，很麻烦。

做法：
  网关维护一份独立档案 /app/data/key-vault.json，结构：
      {"items": [{"id": "...", "name": "...", "key": "sk-...", "created_at": "..."}]}

  什么时候写入：
    1. 用户在页面上「新建密钥」→ 网关先调面板创建拿到明文，再存进档案
    2. 历史上已存在、但档案里没有的密钥 → 无法恢复明文（哈希不可逆），
       页面标为「不可恢复」，并提供「重新生成」按钮

  安全边界（重要）：
    · 档案只存在 /app/data（挂载卷），不会进镜像、不会上传仓库
    · 只有管理员（用登录口令或管理员密钥）才能读到明文
    · 页面默认**打码显示**，点「显示」才展开，避免录屏/截图泄露
    · 删除密钥时同步删档案

  为什么不直接改面板存明文：
    面板是上游编译好的产物，改它风险大、升级会覆盖。
    网关这边加一层档案，既不动上游，也能达到同样效果。
"""
from __future__ import annotations

import json
import os
import time

VAULT_PATH = "/app/data/key-vault.json"


def _read():
    try:
        with open(VAULT_PATH, encoding="utf-8") as f:
            d = json.load(f) or {}
        items = d.get("items")
        return items if isinstance(items, list) else []
    except Exception:
        return []


def _write(items):
    try:
        os.makedirs(os.path.dirname(VAULT_PATH), exist_ok=True)
        tmp = VAULT_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"items": items, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                      f, ensure_ascii=False, indent=2)
        os.replace(tmp, VAULT_PATH)
        try:
            os.chmod(VAULT_PATH, 0o600)
        except Exception:
            pass
        return True
    except Exception:
        return False


def put(item_id, name, key, created_at=""):
    """保存/更新一条明文。同名同 id 覆盖。"""
    if not item_id or not key:
        return False
    items = _read()
    for it in items:
        if it.get("id") == item_id:
            it["name"] = name or it.get("name") or ""
            it["key"] = key
            return _write(items)
    items.append({
        "id": item_id,
        "name": name or "",
        "key": key,
        "created_at": created_at or time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    return _write(items)


def get(item_id):
    for it in _read():
        if it.get("id") == item_id:
            return it.get("key") or ""
    return ""


def remove(item_id):
    items = [it for it in _read() if it.get("id") != item_id]
    return _write(items)


def all_keys():
    """返回 {id: 明文}，供列表接口合并。"""
    return {it.get("id"): it.get("key") for it in _read() if it.get("id")}


def merge_into(items):
    """把档案里的明文合并进面板返回的列表。

    没有明文的（历史遗留）标记 recoverable=False，页面会提示「不可恢复」。
    """
    keys = all_keys()
    out = []
    for it in items or []:
        row = dict(it)
        k = keys.get(it.get("id"))
        row["plain_key"] = k or ""
        row["recoverable"] = bool(k)
        out.append(row)
    return out
