# -*- coding: utf-8 -*-
"""配置读写。路径：%LOCALAPPDATA%\\AutoResume\\config.json"""

import json
import os
from dataclasses import dataclass, asdict, field

APP_DIR_NAME = "AutoResume"


def app_dir():
    """应用数据目录，不存在则创建。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def log_dir():
    path = os.path.join(app_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def config_path():
    return os.path.join(app_dir(), "config.json")


@dataclass
class Config:
    poll_seconds: int = 60
    auto_resume: bool = False
    locked_project: str = ""
    locked_thread: str = ""
    retry_window_minutes: int = 10
    cooldown_seconds: int = 90
    stale_grace_seconds: int = 90
    log_retention_days: int = 30
    continue_text: str = "继续"
    language: str = "zh-CN"
    blocked_confirm_polls: int = 3
    follow_open_thread: bool = False
    autostart: bool = False
    notify_enabled: bool = True

    @classmethod
    def load(cls):
        path = config_path()
        if not os.path.exists(path):
            cfg = cls()
            cfg.save()
            return cfg
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        cfg = cls()
        for key, value in raw.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg

    def save(self):
        path = config_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def lock(self, project, thread):
        self.locked_project = project or ""
        self.locked_thread = thread or ""
        self.save()
