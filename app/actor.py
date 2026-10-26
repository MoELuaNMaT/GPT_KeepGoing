# -*- coding: utf-8 -*-
"""界面动作：刷新阶梯、切换对话、恢复目标、发送继续。

所有操作走 UIA，不用坐标点击，窗口被遮挡也能点。
"""

import time

import uiautomation as auto

from . import constants as C
from . import discovery, planner, reader

MAX_WAIT_THREAD = 10.0


def _buttons(win):
    """收集所有按钮控件（早停，够用即止）。"""
    out = []
    stack = [win]
    while stack:
        c = stack.pop()
        try:
            if c.ControlTypeName == "ButtonControl":
                out.append(c)
                continue
            stack.extend(reversed(c.GetChildren()))
        except Exception:
            continue
    return out


def list_conversations():
    """读侧边栏，返回 [{"project": 名称, "conversations": [标题...]}]。

    侧边栏里每个项目对应一个名字以「中的已安排任务」结尾的 ListControl，
    它的 ListItemControl 子节点就是会话。
    """
    win = discovery.find_window()
    if win is None:
        return []
    nodes = []          # (depth, kind, name, parent_index)
    stack = [(win, 0, -1)]
    count = 0
    while stack and count < 4000:
        ctrl, depth, parent = stack.pop()
        try:
            kind = ctrl.ControlTypeName
        except Exception:
            continue
        name = ""
        if kind in ("ListControl", "ListItemControl"):
            try:
                name = ctrl.Name or ""
            except Exception:
                name = ""
        idx = len(nodes)
        nodes.append({"kind": kind, "name": name, "depth": depth, "parent": parent})
        count += 1
        try:
            children = ctrl.GetChildren()
        except Exception:
            continue
        for ch in reversed(children):
            stack.append((ch, depth + 1, idx))

    result = []
    for i, node in enumerate(nodes):
        if node["kind"] != "ListControl" or not node["name"].endswith("中的已安排任务"):
            continue
        project = node["name"][: -len("中的已安排任务")]
        convs = []
        depth = node["depth"]
        for j in range(i + 1, len(nodes)):
            nxt = nodes[j]
            if nxt["depth"] <= depth:
                break
            if nxt["kind"] == "ListItemControl" and nxt["name"]:
                convs.append(nxt["name"])
        if project and convs:
            result.append({"project": project, "conversations": convs})
    return result


def find_button(win, name):
    for c in _buttons(win):
        try:
            if (c.Name or "") == name:
                return c
        except Exception:
            continue
    return None


def click_button(win, name):
    """按名字点按钮。返回是否点到。"""
    ctrl = find_button(win, name)
    if ctrl is None:
        return False
    try:
        if not ctrl.IsEnabled:
            return False
    except Exception:
        pass
    try:
        ctrl.GetInvokePattern().Invoke()
        return True
    except Exception:
        try:
            ctrl.Click(simulateMove=False)
            return True
        except Exception:
            return False


def _composer(win):
    stack = [win]
    while stack:
        c = stack.pop()
        try:
            if c.ControlTypeName == "EditControl" and C.COMPOSER_CLASS_MARK in (c.ClassName or ""):
                return c
            stack.extend(reversed(c.GetChildren()))
        except Exception:
            continue
    return None


def switch_to_thread(title, timeout=MAX_WAIT_THREAD):
    """点击侧边栏同名对话，并等到标题确实变了。"""
    win = discovery.find_window()
    if win is None:
        return False, "客户端未运行"
    if not click_button(win, title):
        return False, "侧边栏找不到对话: " + title
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.4)
        snap = reader.read()
        if snap.thread == title:
            return True, ""
    return False, "切换对话超时"


def set_composer_text(text):
    """往输入框写文字。中文用剪贴板粘贴，避免输入法干扰。"""
    win = discovery.find_window()
    if win is None:
        return False, "客户端未运行"
    box = _composer(win)
    if box is None:
        return False, "找不到输入框"
    try:
        box.Click(simulateMove=False)
    except Exception:
        return False, "点击输入框失败"
    time.sleep(0.15)
    auto.SendKeys("{Ctrl}a", waitTime=0.05)
    auto.SendKeys("{Delete}", waitTime=0.05)
    if text:
        try:
            old = auto.GetClipboardText()
        except Exception:
            old = ""
        auto.SetClipboardText(text)
        time.sleep(0.05)
        auto.SendKeys("{Ctrl}v", waitTime=0.15)
        time.sleep(0.2)
        try:
            auto.SetClipboardText(old or "")
        except Exception:
            pass
    return True, ""


def read_composer_text():
    win = discovery.find_window()
    if win is None:
        return None
    box = _composer(win)
    if box is None:
        return None
    try:
        vp = box.GetPattern(auto.PatternId.ValuePattern)
        return ((vp.Value if vp else "") or "").rstrip("\n")
    except Exception:
        return None


def send_message():
    """优先点发送按钮；没有按钮时退回回车键。"""
    win = discovery.find_window()
    if win is None:
        return False, "客户端未运行"
    ctrl = find_button(win, "发送") or find_button(win, "发送消息")
    if ctrl is not None:
        try:
            enabled = ctrl.IsEnabled
        except Exception:
            enabled = False
        if enabled:
            try:
                ctrl.GetInvokePattern().Invoke()
                return True, "点击发送按钮"
            except Exception:
                pass
    # 退回回车
    auto.SendKeys("{Enter}", waitTime=0.2)
    return True, "回车发送"


def refresh_ladder(cfg, log, target_thread):
    """强制客户端重新取数。返回 (成功, 用了哪一级, 快照)。

    L1 切到新聊天再切回；L2 重载页面。
    L3（重启客户端）MVP 不做，见 spec 说明。
    """
    if not target_thread:
        return False, "L0", reader.read()
    snap = reader.read()
    if not planner.is_stale(snap, reader._now(), cfg):
        return True, "L0", snap

    log.write("warn", "refresh_start", level_detail="L1", thread=snap.thread)

    win = discovery.find_window()
    if win is not None:
        click_button(win, "新聊天")
        time.sleep(1.5)
        ok, err = switch_to_thread(target_thread)
        if ok:
            snap = reader.read()
            if not planner.is_stale(snap, reader._now(), cfg):
                log.write("info", "refresh_ok", level_detail="L1")
                return True, "L1", snap
        else:
            log.write("warn", "refresh_l1_fail", detail=err)

    # L2：重载页面
    log.write("warn", "refresh_start", level_detail="L2")
    discovery.force_foreground(discovery.find_hwnd())
    auto.SendKeys("{Ctrl}r", waitTime=0.2)
    time.sleep(6.0)
    ok, err = switch_to_thread(target_thread, timeout=15)
    snap = reader.read()
    if not planner.is_stale(snap, reader._now(), cfg):
        log.write("info", "refresh_ok", level_detail="L2")
        return True, "L2", snap
    log.write("error", "refresh_fail", detail="L1/L2 均未刷新")
    return False, "L1/L2", snap


def run_act(cfg, log):
    """执行一次继续。返回 dict(ok, action, detail)。"""
    hwnd = discovery.find_hwnd()
    if not hwnd:
        return {"ok": False, "action": "none", "detail": "客户端未运行"}

    if not discovery.force_foreground(hwnd):
        log.write("warn", "focus_fail")

    # 1) 确保停在锁定对话上
    snap = reader.read()
    if cfg.locked_thread and snap.thread != cfg.locked_thread:
        log.write("info", "switch_back", want=cfg.locked_thread, now_at=snap.thread)
        ok, err = switch_to_thread(cfg.locked_thread)
        if not ok:
            return {"ok": False, "action": "switch", "detail": err}
        snap = reader.read()

    # 2) 界面若陈旧，先强制刷新
    if planner.is_stale(snap, reader._now(), cfg):
        ok, level, snap = refresh_ladder(cfg, log, cfg.locked_thread or snap.thread)

    # 3) 前置条件
    if snap.quota_msgs:
        return {"ok": False, "action": "none", "detail": "额度仍显示用尽"}
    if not snap.composer_empty:
        return {"ok": False, "action": "none", "detail": "输入框有草稿，跳过"}

    action = planner.choose_act(snap)
    if action == "none":
        return {"ok": False, "action": "none", "detail": "目标状态不需要动作: " + snap.goal_status}

    win = discovery.find_window()
    if win is None:
        return {"ok": False, "action": action, "detail": "客户端未运行"}

    if action == "resume_goal":
        if not click_button(win, C.GOAL_RESUME):
            return {"ok": False, "action": action, "detail": "点不到恢复目标"}
        time.sleep(1.2)
        # 可能弹确认框
        win2 = discovery.find_window()
        if win2 is not None and find_button(win2, C.GOAL_RESUME_CONFIRM) is not None:
            click_button(win2, C.GOAL_RESUME_CONFIRM)
            log.write("info", "goal_resume_confirmed")
        return {"ok": True, "action": action, "detail": "点击恢复目标"}

    # 无目标：输入继续并发送
    text = cfg.continue_text or "继续"
    ok, err = set_composer_text(text)
    if not ok:
        return {"ok": False, "action": action, "detail": err}
    got = read_composer_text()
    if got is None or got.strip() != text.strip():
        return {"ok": False, "action": action, "detail": "输入框写入校验失败"}
    ok, how = send_message()
    if not ok:
        return {"ok": False, "action": action, "detail": how}
    return {"ok": True, "action": action, "detail": how}
