# -*- coding: utf-8 -*-
"""按天分文件的 JSONL 日志。"""

import json
import os
import threading
import time
from datetime import datetime, timedelta

from .config import log_dir


class LogBook:
    def __init__(self, retention_days=30):
        self._lock = threading.Lock()
        self.on_write = None          # 界面订阅用
        self.retention_days = retention_days
        self.path = os.path.join(log_dir(), datetime.now().strftime("%Y-%m-%d") + ".jsonl")
        self._prune()

    def _prune(self):
        """删除超过保留期的日志文件。"""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        base = log_dir()
        for name in os.listdir(base):
            if not name.endswith(".jsonl"):
                continue
            try:
                day = datetime.strptime(name[:10], "%Y-%m-%d")
            except ValueError:
                continue
            if day < cutoff:
                try:
                    os.remove(os.path.join(base, name))
                except OSError:
                    pass

    def write(self, level, event, **fields):
        """写一行日志，返回该行对象供界面显示。"""
        now = datetime.now().astimezone()
        record = {"ts": now.isoformat(timespec="seconds"), "level": level, "event": event}
        record.update({k: v for k, v in fields.items() if v is not None})
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            path = os.path.join(log_dir(), now.strftime("%Y-%m-%d") + ".jsonl")
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        if self.on_write is not None:
            self.on_write(record)
        return record
