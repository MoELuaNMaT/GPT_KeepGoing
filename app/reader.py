# -*- coding: utf-8 -*-
"""从 UIA 控件树读出对话快照。

性能要点：只对需要的控件类型读 Name/ClassName/IsEnabled，
其余控件只读 ControlType。这样把 1200 个控件的 COM 调用压到最低。
"""

import re
import time
from dataclasses import dataclass, field

import uiautomation as auto

from . import constants as C
from . import planner
from .discovery import find_window, is_foreground

MAX_NODES = 4000
DEPTH_CAP = 34

# 需要读名字的控件类型
NAMED_KINDS = {
    "ButtonControl", "TextControl", "EditControl", "DocumentControl",
    "ImageControl", "StatusBarControl",
}

# 重置时间的多种写法：
#   19:37
#   2026年10月27日 00:45
#   10月27日 0:45
#   2026-10-27 00:45
RESET_CJK_RE = re.compile(r"(?:(\d{4})年)?\s*(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})")
RESET_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})")
RESET_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")

# 只有出现这些词才认为是在说重置时间，避免把正文里的时刻当重置时间
RESET_HINT_WORDS = ("重置", "后重试", "retry", "resets", "reset at")
PROJECT_RE = re.compile(r"^项目：(.+)$")
CONTEXT_RE = re.compile(r"^上下文用量：(\d+)%$")
GOAL_ELAPSED_RE = re.compile(r"(\d+d \d+h \d+m \d+s)$")


@dataclass
class Item:
    kind: str
    name: str = ""
    cls: str = ""
    enabled: bool = True
    depth: int = 0
    value: str = ""
    off: bool = False


@dataclass
class Snap:
    ok: bool = False
    error: str = ""
    pid: int = 0
    hwnd: int = 0
    foreground: bool = False
    project: str = ""
    thread: str = ""
    model: str = ""
    permission: str = ""
    context_pct: int = -1
    stop_present: bool = False
    approval: list = field(default_factory=list)
    waiting_text: str = ""
    quota_msgs: list = field(default_factory=list)
    reset_clock: str = ""
    reset_at: object = None
    goal_status: str = ""
    goal_objective: str = ""
    goal_actions: list = field(default_factory=list)
    composer_present: bool = False
    composer_empty: bool = True
    send_present: bool = False
    send_enabled: bool = False
    read_ms: int = 0


def _needs_visibility(name):
    """这些文案要判真假，正文里出现同字样不算，所以需要看是否可见。"""
    text = (name or "").strip()
    if text.startswith(C.WAITING_TEXT):
        return True
    return planner.is_quota_text(text)


def _walk(ctrl, depth, out):
    """DFS 收集控件，按类型决定读哪些属性。"""
    if depth > DEPTH_CAP or len(out) >= MAX_NODES:
        return
    try:
        kind = ctrl.ControlTypeName
    except Exception:
        return
    item = Item(kind=kind, depth=depth)
    if kind in NAMED_KINDS:
        try:
            item.name = ctrl.Name or ""
        except Exception:
            item.name = ""
    if kind in ("ButtonControl", "EditControl"):
        try:
            item.cls = ctrl.ClassName or ""
        except Exception:
            item.cls = ""
    if kind == "ButtonControl":
        try:
            item.enabled = bool(ctrl.IsEnabled)
        except Exception:
            item.enabled = True
    if kind == "EditControl":
        # 输入框内容；空框时这里返回的是占位符文本
        try:
            vp = ctrl.GetPattern(auto.PatternId.ValuePattern)
            item.value = (vp.Value if vp else "") or ""
        except Exception:
            item.value = ""
    if kind == "TextControl" and _needs_visibility(item.name):
        # 只有这类候选才多读一次可见性，代价可以忽略
        try:
            item.off = bool(ctrl.IsOffscreen)
        except Exception:
            item.off = False
    out.append(item)
    if len(out) >= MAX_NODES:
        return
    try:
        children = ctrl.GetChildren()
    except Exception:
        return
    for ch in children:
        _walk(ch, depth + 1, out)


def _pause_ms(t0):
    return int((time.time() - t0) * 1000)


def read(win=None):
    """读一次快照。失败时 ok=False 并给出原因。"""
    t0 = time.time()
    snap = Snap()
    try:
        if win is None:
            win = find_window()
        if win is None:
            snap.error = "客户端未运行"
            snap.read_ms = _pause_ms(t0)
            return snap
        snap.pid = win.ProcessId
        snap.hwnd = win.NativeWindowHandle
        snap.foreground = is_foreground(snap.hwnd)
    except Exception as exc:
        snap.error = "读取窗口失败: " + repr(exc)
        snap.read_ms = _pause_ms(t0)
        return snap

    items = []
    try:
        _walk(win, 0, items)
    except Exception as exc:
        snap.error = "遍历控件失败: " + repr(exc)
        snap.read_ms = _pause_ms(t0)
        return snap

    composer_value = ""
    for idx, it in enumerate(items):
        name = it.name
        if it.kind == "EditControl" and C.COMPOSER_CLASS_MARK in it.cls:
            composer_value = it.value
        if not name:
            continue

        if it.kind == "DocumentControl" and not snap.thread:
            # 根 WebArea 的名字就是当前打开的对话标题
            if it.cls == "" and name and len(name) < 200:
                snap.thread = name

        m = PROJECT_RE.match(name)
        if m and it.kind == "ImageControl":
            snap.project = m.group(1).strip()

        m = CONTEXT_RE.match(name)
        if m:
            snap.context_pct = int(m.group(1))

        if it.kind == "ButtonControl" and name == "更改权限":
            # 权限值紧跟在这个按钮后面
            for nxt in items[idx + 1: idx + 7]:
                if nxt.kind == "TextControl" and nxt.name:
                    snap.permission = nxt.name
                    break

        if it.kind == "ButtonControl" and name in C.STOP_LABELS:
            snap.stop_present = True

        if it.kind == "ButtonControl" and name in C.APPROVAL_LABELS:
            if name not in snap.approval:
                snap.approval.append(name)

        # 只认活动状态行本身，且必须当前可见；消息正文里的同名字样不算
        if it.kind == "TextControl" and planner.is_waiting_label(name, it.off):
            snap.waiting_text = name

        # 额度横幅必须当前可见才算；聊天正文里讨论额度不算
        if planner.is_quota_text(name, it.off):
            if name not in snap.quota_msgs:
                snap.quota_msgs.append(name)

        if name in C.GOAL_LABELS:
            snap.goal_status = name

        if it.kind == "ButtonControl" and name in (C.GOAL_RESUME, C.GOAL_PAUSE, C.GOAL_CLEAR, C.GOAL_EDIT):
            if name not in snap.goal_actions:
                snap.goal_actions.append(name)

        if it.kind == "ButtonControl" and name.startswith("目标") and not snap.goal_objective:
            rest = re.sub("^(" + "|".join(C.GOAL_LABELS) + r")\s*", "", name)
            rest = GOAL_ELAPSED_RE.sub("", rest).strip()
            if rest and rest not in C.GOAL_LABELS:
                snap.goal_objective = rest[:200]

        if it.kind == "EditControl" and C.COMPOSER_CLASS_MARK in it.cls:
            snap.composer_present = True
            # 输入框的名字就是占位符
            text = composer_value.rstrip("\n").strip()
            snap.composer_empty = (text == "" or text == name.strip())

        if it.kind == "ButtonControl" and name in C.SEND_LABELS:
            snap.send_present = True
            snap.send_enabled = it.enabled and "opacity-50" not in it.cls

    # 重置时刻
    for msg in snap.quota_msgs:
        reset_at, clock = parse_reset_time(msg, _now())
        if reset_at:
            snap.reset_clock = clock
            snap.reset_at = reset_at
            break

    snap.ok = True
    snap.read_ms = _pause_ms(t0)
    return snap


def _now():
    from datetime import datetime
    return datetime.now().astimezone()


def parse_reset_time(text, now):
    """从界面文案解析重置时刻。返回 (datetime, 展示用原文)。

    支持 19:37、2026年10月27日 00:45、10月27日 0:45、2026-10-27 00:45。
    只有文案里出现"重置/后重试"这类词才解析，避免把正文里的时刻当成重置时间。
    """
    from datetime import timedelta
    if not text:
        return None, ""
    lowered = text.lower()
    if not any(word in lowered for word in RESET_HINT_WORDS):
        return None, ""

    m = RESET_CJK_RE.search(text)
    if m:
        year = int(m.group(1)) if m.group(1) else now.year
        month, day, hour, minute = (int(m.group(i)) for i in (2, 3, 4, 5))
        try:
            target = now.replace(year=year, month=month, day=day, hour=hour,
                                 minute=minute, second=0, microsecond=0)
        except ValueError:
            return None, ""
        if not m.group(1) and target < now - timedelta(hours=1):
            target = target.replace(year=year + 1)
        return target, m.group(0).strip()

    m = RESET_ISO_RE.search(text)
    if m:
        year, month, day, hour, minute = (int(m.group(i)) for i in range(1, 6))
        try:
            target = now.replace(year=year, month=month, day=day, hour=hour,
                                 minute=minute, second=0, microsecond=0)
        except ValueError:
            return None, ""
        return target, m.group(0).strip()

    m = RESET_TIME_RE.search(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)
        return target, m.group(0).strip()

    return None, ""
