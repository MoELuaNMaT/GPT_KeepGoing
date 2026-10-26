# -*- coding: utf-8 -*-
"""发现 ChatGPT 窗口，以及窗口焦点控制。

找窗口用 Win32 枚举（毫秒级），不用 UIA 遍历顶层窗口（跨进程调用很慢）。
找到句柄后再用 UIA 包装它，只付一次开销。
"""

import ctypes
import time
from ctypes import wintypes

import psutil
import uiautomation as auto

from .constants import PROCESS_NAME, WINDOW_CLASS

_user32 = ctypes.windll.user32
SW_RESTORE = 9
VK_MENU = 0x12

_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

_cached_hwnd = 0


def chatgpt_pids():
    """所有 ChatGPT 进程的 pid。"""
    pids = set()
    for proc in psutil.process_iter(["pid", "name"]):
        if (proc.info["name"] or "").lower() == PROCESS_NAME.lower():
            pids.add(proc.info["pid"])
    return pids


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _title(hwnd):
    length = _user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _rect_area(hwnd):
    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return 0
    return max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)


def find_hwnd():
    """返回主窗口句柄；找不到返回 0。"""
    global _cached_hwnd
    pids = chatgpt_pids()
    if not pids:
        _cached_hwnd = 0
        return 0
    if _cached_hwnd and _user32.IsWindow(_cached_hwnd):
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(_cached_hwnd, ctypes.byref(pid))
        if pid.value in pids:
            return _cached_hwnd

    found = []

    def callback(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        if _class_name(hwnd) != WINDOW_CLASS:
            return True
        if not _title(hwnd):
            return True
        found.append(hwnd)
        return True

    _user32.EnumWindows(_WNDENUMPROC(callback), 0)
    if not found:
        _cached_hwnd = 0
        return 0
    best = max(found, key=_rect_area)
    _cached_hwnd = best
    return best


def find_window():
    """返回主窗口的 UIA 控件；找不到返回 None。"""
    hwnd = find_hwnd()
    if not hwnd:
        return None
    try:
        return auto.ControlFromHandle(hwnd)
    except Exception:
        return None


def is_foreground(hwnd):
    return _user32.GetForegroundWindow() == hwnd


def force_foreground(hwnd):
    """把窗口拉到前台，返回是否成功。

    前台锁定（ForegroundLockTimeout）会让 SetForegroundWindow 静默失败，
    失败时先按一次 ALT 再重试。
    """
    try:
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.3)
        _user32.SetForegroundWindow(hwnd)
        time.sleep(0.35)
        if is_foreground(hwnd):
            return True
        _user32.keybd_event(VK_MENU, 0, 0, 0)
        _user32.keybd_event(VK_MENU, 0, 2, 0)
        time.sleep(0.1)
        _user32.SetForegroundWindow(hwnd)
        time.sleep(0.35)
        return is_foreground(hwnd)
    except Exception:
        return False


def current_foreground():
    return _user32.GetForegroundWindow()


def focus_window(hwnd):
    """恢复并置前，用于需要键盘输入的场景。"""
    return force_foreground(hwnd)
