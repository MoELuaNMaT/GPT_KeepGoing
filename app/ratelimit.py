# -*- coding: utf-8 -*-
"""从 Codex 本地会话记录读额度余额。

Codex 每次拿到模型响应都会在 rollout JSONL 里记一条 rate_limits：
  primary   窗口 300 分钟（5 小时），有 used_percent 与 resets_at
  secondary 窗口 10080 分钟（7 天），同上
resets_at 是 Unix 时间戳。这里只读，不写客户端任何数据。
"""

import glob
import io
import json
import os
from datetime import datetime, timedelta

MAX_TAIL_BYTES = 2 * 1024 * 1024
TAIL_DAYS = 3


def sessions_root():
    base = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    return os.path.join(base, "sessions")


def _recent_files(days=TAIL_DAYS):
    """最近几天的 rollout 文件，按修改时间倒序。只扫最近日期目录，避免全盘遍历。"""
    root = sessions_root()
    if not os.path.isdir(root):
        return []
    files = []
    today = datetime.now()
    for offset in range(days + 1):
        day = today - timedelta(days=offset)
        pattern = os.path.join(root, day.strftime("%Y"), day.strftime("%m"), day.strftime("%d"), "*.jsonl")
        files.extend(glob.glob(pattern))
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files


def _find_rate_limits(node):
    """在解析后的 JSON 里递归找 rate_limits。"""
    if isinstance(node, dict):
        if "rate_limits" in node and isinstance(node["rate_limits"], dict):
            return node["rate_limits"]
        for value in node.values():
            found = _find_rate_limits(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_rate_limits(value)
            if found is not None:
                return found
    return None


def _read_tail_lines(path):
    """读文件尾部若干行，跳过第一行（可能是被截断的半行）。"""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > MAX_TAIL_BYTES:
            f.seek(size - MAX_TAIL_BYTES)
        raw = f.read()
    text = raw.decode("utf-8", "replace")
    lines = text.split("\n")
    return lines[1:] if size > MAX_TAIL_BYTES else lines


def _window(raw):
    """把 primary/secondary 转成结构。remaining 是剩余百分比。"""
    if not isinstance(raw, dict):
        return None
    used = raw.get("used_percent")
    resets_at = raw.get("resets_at")
    minutes = raw.get("window_minutes")
    remaining = None
    if isinstance(used, (int, float)):
        remaining = max(0.0, min(100.0, 100.0 - float(used)))
    reset_dt = None
    if isinstance(resets_at, (int, float)):
        reset_dt = datetime.fromtimestamp(resets_at).astimezone()
    return {
        "used_percent": float(used) if isinstance(used, (int, float)) else None,
        "remaining_percent": remaining,
        "window_minutes": int(minutes) if isinstance(minutes, (int, float)) else None,
        "resets_at": reset_dt.isoformat(timespec="seconds") if reset_dt else None,
    }


def parse_record(payload, observed_at=None):
    """把一条 rate_limits 转成对外结构。纯函数，便于测试。"""
    if not isinstance(payload, dict):
        return None
    five = _window(payload.get("primary"))
    week = _window(payload.get("secondary"))
    if five is None and week is None:
        return None
    credits = payload.get("credits") or {}
    return {
        "ok": True,
        "plan_type": payload.get("plan_type"),
        "limit_id": payload.get("limit_id"),
        "five_hour": five,
        "weekly": week,
        "credits_balance": credits.get("balance"),
        "observed_at": observed_at,
    }


def read_limits():
    """读最新一条额度记录。找不到时 ok=False。"""
    for path in _recent_files()[:8]:
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(path)).astimezone()
            for line in reversed(_read_tail_lines(path)):
                if "rate_limits" not in line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                found = _find_rate_limits(obj)
                if found is None:
                    continue
                result = parse_record(found, mtime.isoformat(timespec="seconds"))
                if result:
                    result["source"] = os.path.basename(path)
                    return result
        except OSError:
            continue
    return {"ok": False, "error": "没有找到额度记录"}
