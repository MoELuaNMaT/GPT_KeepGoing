# -*- coding: utf-8 -*-
"""自动续跑助手启动入口。单实例、配置、日志、托盘、界面、调度线程在这里装配。"""

import ctypes
import queue
import sys
import tkinter as tk
from tkinter import messagebox

from app.config import Config, app_dir
from app.engine import Engine
from app.logbook import LogBook
from app.notify import Notifier
from app.tray import Tray
from app.ui import Dashboard

MUTEX_NAME = "Global\\AutoResumeAssistant"
ERROR_ALREADY_EXISTS = 183


def single_instance():
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return handle, ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS


def main():
    handle, existed = single_instance()
    if existed:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("自动续跑助手", "已经有一个实例在运行。")
        root.destroy()
        return 0

    cfg = Config.load()
    events = queue.Queue()
    log = LogBook(retention_days=cfg.log_retention_days)
    log.on_write = lambda rec: events.put({"type": "log", "record": rec})

    root = tk.Tk()
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
    except Exception:
        hwnd = 0
    notifier = Notifier(hwnd, log)
    engine = Engine(cfg, log, events.put, notifier)

    tray = Tray(
        on_show=lambda: events.put({"type": "cmd", "cmd": "show"}),
        on_act=lambda: events.put({"type": "cmd", "cmd": "act"}),
        on_quit=lambda: events.put({"type": "cmd", "cmd": "quit"}),
        logbook=log,
    )
    tray_ok = tray.start()

    ui = Dashboard(root, cfg, log, engine, events, tray if tray_ok else None)
    engine.start()

    log.write("info", "app_start", dir=app_dir(), auto_resume=cfg.auto_resume,
              tray=tray_ok, locked=cfg.locked_thread or None)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
