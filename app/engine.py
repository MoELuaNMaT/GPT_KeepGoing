# -*- coding: utf-8 -*-
"""调度引擎：后台线程，按状态机轮询与执行。"""

import threading
import time
from datetime import datetime

import uiautomation as auto

from . import actor, constants as C, discovery, i18n, planner, ratelimit, reader


class Engine(threading.Thread):
    def __init__(self, cfg, logbook, emit, notifier=None):
        super().__init__(daemon=True, name="auto-resume-engine")
        self.cfg = cfg
        self.log = logbook
        self.emit = emit
        self.notifier = notifier
        self._stop = threading.Event()
        self.enabled = bool(cfg.auto_resume)
        self.phase = C.PHASE_MONITOR if self.enabled else C.PHASE_OFF
        self.prev_state = ""
        self.due_at = time.time()
        self.attempts = 0
        self.halted = False
        self._last_notify = None
        self._manual = False
        self.snap = None
        self.balance = {"ok": False}
        self.last_reset = None         # 上次从横幅读到的重置时刻，跨轮次缓存
        self.last_reset_clock = ""

    # ---------- 外部控制 ----------

    def stop(self):
        self._stop.set()

    def set_enabled(self, value, snap=None):
        """开关切换。开启时锁住当前对话。"""
        if value:
            self.enabled = True
            self.halted = False
            self.attempts = 0
            self.phase = C.PHASE_MONITOR
            self.prev_state = ""
            self.due_at = time.time()
            self.cfg.auto_resume = True
            if snap is not None and snap.thread:
                self.cfg.lock(snap.project, snap.thread)
            else:
                self.cfg.save()
        else:
            self.enabled = False
            self.phase = C.PHASE_OFF
            self.cfg.auto_resume = False
            self.cfg.save()

    def request_act_now(self):
        """立刻执行一次续跑（手动）。绕过定时与重试计数。"""
        self.halted = False
        self.attempts = 0
        self._manual = True
        self.due_at = 0

    def set_target(self, project, thread):
        """从会话列表里选目标对话。"""
        self.cfg.lock(project, thread)
        self.prev_state = ""
        self.phase = C.PHASE_MONITOR
        self.due_at = 0

    # ---------- 主循环 ----------

    def run(self):
        auto.InitializeUIAutomationInCurrentThread()
        try:
            while not self._stop.is_set():
                if time.time() >= self.due_at:
                    try:
                        self._cycle()
                    except Exception as exc:
                        self.log.write("error", "cycle_error", detail=repr(exc))
                        self.due_at = time.time() + 30
                time.sleep(0.25)
        finally:
            auto.UninitializeUIAutomationInCurrentThread()

    def _publish(self, snap, state):
        self.snap = snap
        payload = {
            "type": "snapshot",
            "ok": snap.ok,
            "project": snap.project,
            "thread": snap.thread,
            "state": state,
            "phase": self.phase,
            "language": self.cfg.language,
            "reset_clock": snap.reset_clock,
            "reset_at": snap.reset_at,
            "read_ms": snap.read_ms,
            "goal_status": snap.goal_status,
            "composer_empty": snap.composer_empty,
            "send_present": snap.send_present,
            "target": self.cfg.locked_thread,
            "target_project": self.cfg.locked_project,
            "follow": bool(self.cfg.follow_open_thread),
            "balance": self.balance,
        }
        self.emit(payload)

    def _cycle(self):
        snap = reader.read()
        state = planner.classify(snap)
        try:
            self.balance = ratelimit.read_limits()
        except Exception as exc:
            self.balance = {"ok": False, "error": repr(exc)}

        # 横幅有时会丢掉重置时刻，缓存上一次读到的值，避免调度逻辑跟着抖
        if snap.reset_at is not None:
            self.last_reset = snap.reset_at
            self.last_reset_clock = snap.reset_clock
        elif state == C.ST_QUOTA and self.last_reset is not None:
            snap.reset_at = self.last_reset
            snap.reset_clock = self.last_reset_clock
        elif state != C.ST_QUOTA:
            self.last_reset = None
            self.last_reset_clock = ""

        # 开关关闭：只做展示，不参与决策，也不动作
        if not self.enabled:
            self.phase = C.PHASE_OFF
            self._publish(snap, state)
            if state != self.prev_state:
                self.log.write("info", "poll", state=state, phase=C.PHASE_OFF,
                               read_ms=snap.read_ms, thread=snap.thread or None)
                self.prev_state = state
            self.due_at = time.time() + max(2, int(self.cfg.poll_seconds))
            return

        # 开关刚打开时锁定当前对话
        if not self.cfg.locked_thread and snap.thread:
            self.cfg.lock(snap.project, snap.thread)
            self.log.write("info", "thread_locked", thread=snap.thread, project=snap.project)

        # 跟随模式：把目标同步成当前打开的对话
        if self.cfg.follow_open_thread and snap.thread and snap.thread != self.cfg.locked_thread:
            self.cfg.lock(snap.project, snap.thread)
            self.prev_state = ""
            self.log.write("info", "thread_followed", thread=snap.thread, project=snap.project)

        # 目标对话不是当前打开的那个：绝不把当前对话的状态算到目标上
        if snap.ok and self.cfg.locked_thread and snap.thread and snap.thread != self.cfg.locked_thread:
            self.phase = C.PHASE_LOCKED_NOT_OPEN
            self._publish(snap, C.ST_LOCKED_NOT_OPEN)
            if self.prev_state != C.ST_LOCKED_NOT_OPEN:
                self.log.write("warn", "locked_not_open",
                               target=self.cfg.locked_thread, now_at=snap.thread)
                self.prev_state = C.ST_LOCKED_NOT_OPEN
            self.due_at = time.time() + max(2, int(self.cfg.poll_seconds))
            return

        # 手动「立即续跑」：不看计划，直接执行一次
        if self._manual:
            self._manual = False
            self._publish(snap, state)
            self.log.write("info", "manual_act", state=state)
            self._execute(manual=True)
            self.prev_state = state
            return

        plan = planner.plan_after_poll(snap, self.phase, self.prev_state, reader._now(), self.cfg)
        self.phase = plan["phase"]
        self._publish(snap, state)

        self.log.write("info", "poll", state=state, phase=plan["phase"],
                       read_ms=snap.read_ms,
                       thread=snap.thread or None,
                       reset_clock=snap.reset_clock or None,
                       goal_status=snap.goal_status or None)

        # 通知去重
        if plan["notify"]:
            if plan["notify"] != self._last_notify:
                title = i18n.t(self.cfg.language, "app_title")
                body = i18n.t(self.cfg.language, "notify_" + plan["notify"])
                self._notify(title, body, "warn")
                self._last_notify = plan["notify"]
        else:
            self._last_notify = None

        if plan["act"] and not self.halted:
            self._execute()
        else:
            self.due_at = time.time() + max(2, plan["due_in"])
        self.prev_state = state

    def _execute(self, manual=False):
        self.phase = C.PHASE_ACT
        self.emit({"type": "phase", "phase": self.phase, "phase_text": "正在执行继续"})
        res = actor.run_act(self.cfg, self.log, expect_reset_at=self.last_reset)
        level = "info" if res["ok"] else "warn"
        self.log.write(level, "act", action=res["action"], ok=res["ok"],
                       detail=res["detail"], manual=manual or None)

        if res["ok"]:
            self.attempts = 0
            self.phase = C.PHASE_COOLDOWN
            self.due_at = time.time() + int(self.cfg.cooldown_seconds)
            return

        if manual:
            # 手动触发不计入自动重试窗口
            self.phase = C.PHASE_MONITOR
            self.due_at = time.time() + int(self.cfg.poll_seconds)
            return

        self.attempts += 1
        limit = max(1, int(self.cfg.retry_window_minutes))
        if self.attempts >= limit:
            self.halted = True
            self.phase = C.PHASE_NEEDS_HUMAN
            self.due_at = time.time() + 3600
            lang = self.cfg.language
            self._notify(i18n.t(lang, "notify_halt_title"),
                         i18n.t(lang, "notify_halt_body", n=limit, detail=res["detail"]),
                         "error")
        else:
            self.phase = C.PHASE_REFRESH
            self.due_at = time.time() + 60

    def _notify(self, title, text, level="info"):
        if self.notifier is None:
            return
        if not self.notifier.notify(title, text, level):
            self.emit({"type": "banner", "text": title + "：" + text})
