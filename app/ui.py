# -*- coding: utf-8 -*-
"""仪表盘界面（tkinter）。文案全部走 i18n，切换语言时整窗刷新。"""

import os
import queue
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

from . import actor, autostart, constants as C, i18n
from .config import log_dir

FONT = ("Microsoft YaHei UI", 10)
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_TITLE = ("Microsoft YaHei UI", 12, "bold")
FONT_MONO = ("Consolas", 9)
MAX_LOG_LINES = 20

STATE_COLOR = {
    C.ST_RUNNING: "#1f6feb",
    C.ST_QUOTA: "#d97706",
    C.ST_NEEDS_PERMISSION: "#dc2626",
    C.ST_NEEDS_REPLY: "#dc2626",
    C.ST_IDLE: "#6b7280",
    C.ST_APP_MISSING: "#4b5563",
    C.ST_LOCKED_NOT_OPEN: "#b45309",
}


def _parse_iso(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class LanguageDialog(tk.Toplevel):
    """语言选择弹窗。列表里每种语言用它自己的文字书写。"""

    def __init__(self, master, lang):
        super().__init__(master)
        self.result = None
        self.title(i18n.t(lang, "lang_title"))
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        tk.Label(self, text=i18n.t(lang, "lang_pick"), font=FONT).pack(
            anchor="w", padx=16, pady=(14, 6))

        self.names = [i18n.LANG_NATIVE[code] for code in i18n.LANG_ORDER]
        self.codes = {i18n.LANG_NATIVE[code]: code for code in i18n.LANG_ORDER}
        self.cmb = ttk.Combobox(self, state="readonly", values=self.names,
                                font=FONT, width=26)
        self.cmb.set(i18n.LANG_NATIVE[i18n.normalize(lang)])
        self.cmb.pack(anchor="w", padx=16)

        tk.Label(self, text=i18n.t(lang, "lang_note"), font=FONT_SMALL,
                 fg="#6b7280", justify="left", wraplength=320).pack(
            anchor="w", padx=16, pady=(10, 0))

        row = tk.Frame(self)
        row.pack(anchor="e", padx=16, pady=14)
        tk.Button(row, text=i18n.t(lang, "lang_cancel"), width=10,
                  command=self._cancel).pack(side="left", padx=6)
        tk.Button(row, text=i18n.t(lang, "lang_ok"), width=10,
                  command=self._ok).pack(side="left")

        self.update_idletasks()
        self.geometry("+" + str(master.winfo_rootx() + 60) + "+" + str(master.winfo_rooty() + 60))
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _ok(self):
        self.result = self.codes.get(self.cmb.get())
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class ConfirmDialog(tk.Toplevel):
    """开启自动继续前的确认框。"""

    def __init__(self, master, lang):
        super().__init__(master)
        self.result = False
        self.title(i18n.t(lang, "confirm_title"))
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        tk.Label(self, text=i18n.t(lang, "confirm_title"), font=FONT_TITLE).pack(
            anchor="w", padx=16, pady=(14, 6))
        tk.Label(self, text=i18n.t(lang, "confirm_body"), font=FONT_SMALL,
                 justify="left", wraplength=430).pack(anchor="w", padx=16)
        row = tk.Frame(self)
        row.pack(anchor="e", padx=16, pady=14)
        tk.Button(row, text=i18n.t(lang, "confirm_cancel"), width=10,
                  command=self._cancel).pack(side="left", padx=6)
        tk.Button(row, text=i18n.t(lang, "confirm_ok"), width=18,
                  command=self._ok).pack(side="left")

        self.update_idletasks()
        self.geometry("+" + str(master.winfo_rootx() + 40) + "+" + str(master.winfo_rooty() + 40))
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _ok(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()


class Dashboard:
    def __init__(self, root, cfg, logbook, engine, events, tray=None):
        self.root = root
        self.cfg = cfg
        self.log = logbook
        self.engine = engine
        self.events = events
        self.tray = tray
        self.last_reset_at = None
        self.last_balance = {"ok": False}
        self.banner_text = ""
        self.thread_map = {}
        self._i18n = []          # (widget, key) 供切换语言时刷新
        self.lang = i18n.normalize(cfg.language)

        root.geometry("580x780")
        root.minsize(520, 700)
        root.title(i18n.t(self.lang, "app_title"))
        self._build()
        self._apply_language_texts()

        self.var_resume = tk.BooleanVar(value=bool(cfg.auto_resume))
        self.chk_resume = tk.Checkbutton(
            self.frm_toggle, text="", font=FONT,
            variable=self.var_resume, command=self._on_toggle)
        self.chk_resume.pack(anchor="w", padx=10, pady=(2, 0))
        self._i18n.append((self.chk_resume, "chk_auto"))
        self.lbl_phase = tk.Label(self.frm_toggle, text="", font=FONT_SMALL, fg="#6b7280")
        self.lbl_phase.pack(anchor="w", padx=10, pady=(0, 6))

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._drain()
        self._tick()
        root.after(600, self.refresh_threads)

    # ---------- 布局 ----------

    def _build(self):
        pad = {"padx": 12}

        top = tk.Frame(self.root)
        top.pack(fill="x", pady=(10, 0))
        head = tk.Frame(top)
        head.pack(fill="x", **pad)
        self.lbl_target = tk.Label(head, text="", font=FONT_SMALL, fg="#6b7280")
        self.lbl_target.pack(side="left")
        self._i18n.append((self.lbl_target, "lbl_target"))
        self.btn_lang = tk.Button(head, text="", font=FONT_SMALL, command=self._open_language)
        self.btn_lang.pack(side="right")
        self._i18n.append((self.btn_lang, "btn_language"))

        row = tk.Frame(top)
        row.pack(fill="x", **pad)
        self.cmb = ttk.Combobox(row, state="readonly", font=FONT_SMALL)
        self.cmb.pack(side="left", fill="x", expand=True)
        self.cmb.bind("<<ComboboxSelected>>", self._on_pick)
        self.btn_refresh = tk.Button(row, text="", width=6, command=self.refresh_threads)
        self.btn_refresh.pack(side="left", padx=4)
        self._i18n.append((self.btn_refresh, "btn_refresh"))
        self.btn_current = tk.Button(row, text="", width=8, command=self._use_current)
        self.btn_current.pack(side="left")
        self._i18n.append((self.btn_current, "btn_use_current"))

        self.lbl_thread = tk.Label(top, text="", font=FONT_TITLE)
        self.lbl_thread.pack(anchor="w", **pad)
        self.lbl_project = tk.Label(top, text="", font=FONT_SMALL, fg="#6b7280")
        self.lbl_project.pack(anchor="w", **pad)

        mid = tk.Frame(self.root)
        mid.pack(fill="x", pady=(8, 0))
        self.lbl_status = tk.Label(mid, text="", font=FONT_SMALL, fg="#6b7280")
        self.lbl_status.pack(anchor="w", **pad)
        self._i18n.append((self.lbl_status, "lbl_status"))
        self.lbl_state = tk.Label(mid, text="—", font=FONT_TITLE)
        self.lbl_state.pack(anchor="w", **pad)
        self.lbl_goal = tk.Label(mid, text="", font=FONT_SMALL, fg="#6b7280")
        self.lbl_goal.pack(anchor="w", **pad)

        quota = tk.Frame(self.root)
        quota.pack(fill="x", pady=(6, 0))
        self.lbl_quota = tk.Label(quota, text="", font=FONT_SMALL, fg="#6b7280")
        self.lbl_quota.pack(anchor="w", **pad)
        self._i18n.append((self.lbl_quota, "lbl_quota"))
        self.lbl_reset = tk.Label(quota, text="—", font=FONT)
        self.lbl_reset.pack(anchor="w", **pad)

        # 余额
        bal = tk.Frame(self.root)
        bal.pack(fill="x", pady=(8, 0))
        self.lbl_balance = tk.Label(bal, text="", font=FONT_SMALL, fg="#6b7280")
        self.lbl_balance.pack(anchor="w", **pad)
        self._i18n.append((self.lbl_balance, "lbl_balance"))
        grid = tk.Frame(bal)
        grid.pack(fill="x", **pad)
        self.lbl_bal_5h_name = tk.Label(grid, text="", font=FONT_SMALL, fg="#6b7280", width=10, anchor="w")
        self.lbl_bal_5h_name.grid(row=0, column=0, sticky="w")
        self._i18n.append((self.lbl_bal_5h_name, "lbl_five_hour"))
        self.lbl_bal_5h = tk.Label(grid, text="—", font=FONT, anchor="w")
        self.lbl_bal_5h.grid(row=0, column=1, sticky="w")
        self.lbl_bal_wk_name = tk.Label(grid, text="", font=FONT_SMALL, fg="#6b7280", width=10, anchor="w")
        self.lbl_bal_wk_name.grid(row=1, column=0, sticky="w")
        self._i18n.append((self.lbl_bal_wk_name, "lbl_weekly"))
        self.lbl_bal_wk = tk.Label(grid, text="—", font=FONT, anchor="w")
        self.lbl_bal_wk.grid(row=1, column=1, sticky="w")
        self.lbl_bal_time = tk.Label(bal, text="", font=FONT_SMALL, fg="#9ca3af")
        self.lbl_bal_time.pack(anchor="w", **pad)

        self.frm_toggle = tk.Frame(self.root, bd=1, relief="solid")
        self.frm_toggle.pack(fill="x", pady=(8, 0), **pad)

        opt = tk.Frame(self.root)
        opt.pack(fill="x", pady=(6, 0), **pad)
        self.var_follow = tk.BooleanVar(value=bool(self.cfg.follow_open_thread))
        self.chk_follow = tk.Checkbutton(opt, text="", font=FONT_SMALL,
                                         variable=self.var_follow, command=self._on_follow)
        self.chk_follow.pack(anchor="w")
        self._i18n.append((self.chk_follow, "chk_follow"))
        self.var_auto = tk.BooleanVar(value=autostart.is_enabled())
        self.chk_auto = tk.Checkbutton(opt, text="", font=FONT_SMALL,
                                       variable=self.var_auto, command=self._on_autostart)
        self.chk_auto.pack(anchor="w")
        self._i18n.append((self.chk_auto, "chk_autostart"))

        self.lbl_hint = tk.Label(self.root, text="", font=FONT_SMALL, fg="#b45309",
                                 wraplength=530, justify="left")
        self.lbl_hint.pack(fill="x", pady=(6, 0), **pad)

        logf = tk.Frame(self.root)
        logf.pack(fill="both", expand=True, pady=(4, 0), **pad)
        self.lbl_log = tk.Label(logf, text="", font=FONT_SMALL, fg="#6b7280")
        self.lbl_log.pack(anchor="w")
        self._i18n.append((self.lbl_log, "lbl_log"))
        self.txt = tk.Text(logf, height=7, font=FONT_MONO, wrap="none",
                           state="disabled", bd=0)
        self.txt.pack(fill="both", expand=True)

        bottom = tk.Frame(self.root)
        bottom.pack(fill="x", pady=10, **pad)
        self.btn_act = tk.Button(bottom, text="", width=12, command=self._act_now)
        self.btn_act.pack(side="left")
        self._i18n.append((self.btn_act, "btn_act_now"))
        self.btn_check = tk.Button(bottom, text="", width=12, command=self._check_now)
        self.btn_check.pack(side="left", padx=8)
        self._i18n.append((self.btn_check, "btn_check_now"))
        self.btn_logs = tk.Button(bottom, text="", width=14,
                                  command=lambda: os.startfile(log_dir()))
        self.btn_logs.pack(side="left")
        self._i18n.append((self.btn_logs, "btn_open_logs"))

    # ---------- 多语言 ----------

    def _apply_language_texts(self):
        """把当前语言应用到所有登记的控件。"""
        for widget, key in self._i18n:
            try:
                widget.configure(text=i18n.t(self.lang, key))
            except tk.TclError:
                pass

    def _retranslate(self):
        self.lang = i18n.normalize(self.cfg.language)
        self.root.title(i18n.t(self.lang, "app_title"))
        self._apply_language_texts()
        self._render_state_labels()
        self._render_goal_label()
        self._render_balance(self.last_balance, getattr(self, "_quota_reset_at", None))
        self._render_hint()

    def _open_language(self):
        dlg = LanguageDialog(self.root, self.lang)
        self.root.wait_window(dlg)
        if not dlg.result or dlg.result == self.lang:
            return
        self.cfg.language = dlg.result
        self.cfg.continue_text = i18n.continue_text(dlg.result)
        self.cfg.save()
        self._retranslate()
        self._append("language", i18n.t(self.lang, "log_language",
                                        name=i18n.LANG_NATIVE[self.lang]))

    # ---------- 交互 ----------

    def refresh_threads(self):
        try:
            groups = actor.list_conversations()
        except Exception:
            groups = []
        values = []
        self.thread_map = {}
        for group in groups:
            for conv in group["conversations"]:
                label = group["project"] + " / " + conv
                values.append(label)
                self.thread_map[label] = (group["project"], conv)
        self.cmb["values"] = values
        if values and not self.cmb.get():
            current = self.cfg.locked_project + " / " + self.cfg.locked_thread
            if current in values:
                self.cmb.set(current)
        if not values:
            self.lbl_hint.configure(text=i18n.t(self.lang, "hint_no_threads"))

    def _on_pick(self, _evt=None):
        label = self.cmb.get()
        if label not in self.thread_map:
            return
        project, conv = self.thread_map[label]
        self.engine.set_target(project, conv)
        self._render_thread_labels(conv, project, conv)

    def _use_current(self):
        snap = self.engine.snap
        if snap is None or not snap.thread:
            messagebox.showinfo(i18n.t(self.lang, "app_title"),
                                i18n.t(self.lang, "hint_need_read"))
            return
        self.engine.set_target(snap.project, snap.thread)
        self._render_thread_labels(snap.thread, snap.project, snap.thread)
        self.cmb.set("")

    def _on_toggle(self):
        lang = self.lang
        if self.var_resume.get():
            dlg = ConfirmDialog(self.root, lang)
            self.root.wait_window(dlg)
            if not dlg.result:
                self.var_resume.set(False)
                return
            self.cfg.auto_resume = True
            self.engine.set_enabled(True, self.engine.snap)
            self._append("toggle", i18n.t(lang, "log_toggle_on"))
        else:
            self.engine.set_enabled(False)
            self._append("toggle", i18n.t(lang, "log_toggle_off"))

    def _on_follow(self):
        self.cfg.follow_open_thread = bool(self.var_follow.get())
        self.cfg.save()
        word = i18n.t(self.lang, "word_on" if self.cfg.follow_open_thread else "word_off")
        self._append("follow", i18n.t(self.lang, "log_follow", state=word))
        self.engine.due_at = 0

    def _on_autostart(self):
        want = bool(self.var_auto.get())
        try:
            if want:
                autostart.enable()
            else:
                autostart.disable()
            self.cfg.autostart = want
            self.cfg.save()
            word = i18n.t(self.lang, "word_on" if want else "word_off")
            self._append("autostart", i18n.t(self.lang, "log_autostart", state=word))
        except Exception as exc:
            self.var_auto.set(not want)
            messagebox.showerror(i18n.t(self.lang, "app_title"),
                                 "autostart: " + repr(exc))

    def _act_now(self):
        self.engine.request_act_now()
        self._append("manual_act", i18n.t(self.lang, "log_manual_act"))

    def _check_now(self):
        self.engine.due_at = 0
        self._append("manual_check", i18n.t(self.lang, "log_manual_check"))

    def _on_close(self):
        if self.tray is not None:
            self.root.withdraw()
        else:
            self.quit_app()

    def quit_app(self):
        try:
            self.engine.stop()
        except Exception:
            pass
        if self.tray is not None:
            self.tray.stop()
        self.root.destroy()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.focus_force()
        except Exception:
            pass

    # ---------- 事件 ----------

    def _drain(self):
        try:
            while True:
                evt = self.events.get_nowait()
                kind = evt.get("type")
                if kind == "snapshot":
                    self._on_snapshot(evt)
                elif kind == "log":
                    rec = evt["record"]
                    self._append(rec.get("event", ""), self._summarize(rec),
                                 ts=rec.get("ts", ""), level=rec.get("level", "info"))
                elif kind == "banner":
                    self.banner_text = evt.get("text", "")
                    self.lbl_hint.configure(text=self.banner_text)
                elif kind == "cmd":
                    self._on_command(evt.get("cmd"))
                elif kind == "disabled":
                    self.var_resume.set(False)
                    reason = evt.get("reason") or ""
                    self._append("goal_terminal",
                                 i18n.goal_text(self.lang, reason) if reason else "")
        except queue.Empty:
            pass
        self.root.after(200, self._drain)

    def _on_command(self, cmd):
        if cmd == "show":
            self.show_window()
        elif cmd == "act":
            self.show_window()
            self._act_now()
        elif cmd == "quit":
            self.quit_app()

    def _on_snapshot(self, evt):
        self.last_snapshot = evt
        thread = evt.get("thread") or ""
        target = evt.get("target") or ""
        self._render_thread_labels(target or thread, evt.get("target_project") or evt.get("project"), thread)
        self._last_state = evt.get("state")
        self._last_phase = evt.get("phase")
        self._last_goal_mode = evt.get("goal_mode") or C.GM_NONE
        self._last_goal_end = evt.get("goal_end")
        self.last_reset_at = self._reset_from(evt)
        self._quota_reset_at = self.last_reset_at
        self._render_state_labels()
        self._render_goal_label()
        self._render_balance(evt.get("balance") or {"ok": False}, self.last_reset_at)
        self._render_hint()
        if self.tray is not None:
            self.tray.set_tooltip(
                i18n.t(self.lang, "app_title") + " · " +
                i18n.state_text(self.lang, evt.get("state")) +
                ((" · " + target) if target else ""))

    def _reset_from(self, evt):
        value = evt.get("reset_at")
        if isinstance(value, str):
            return _parse_iso(value)
        return value

    def _render_thread_labels(self, thread, project, open_thread):
        self.lbl_thread.configure(text=thread or i18n.t(self.lang, "hint_not_locked"))
        self.lbl_project.configure(text=project or "")
        self._open_thread = open_thread or ""

    def _render_state_labels(self):
        state = getattr(self, "_last_state", None)
        phase = getattr(self, "_last_phase", None)
        if state:
            self.lbl_state.configure(text=i18n.state_text(self.lang, state),
                                     fg=STATE_COLOR.get(state, "#111827"))
        if phase:
            self.lbl_phase.configure(text=i18n.phase_text(self.lang, phase))
        if self.last_reset_at:
            self.lbl_reset.configure(
                text=self.last_reset_at.strftime("%H:%M") + "（" +
                     self.last_reset_at.strftime("%Y-%m-%d %H:%M") + "）")
        elif state == C.ST_QUOTA:
            self.lbl_reset.configure(text=i18n.t(self.lang, "reset_unknown"), fg="#b45309")

    def _render_goal_label(self):
        """显示目标模式；受阻或完成时带上发生时间。"""
        mode = getattr(self, "_last_goal_mode", C.GM_NONE) or C.GM_NONE
        end = getattr(self, "_last_goal_end", None) or {}
        text = i18n.goal_text(self.lang, mode)
        if end.get("mode") == mode and end.get("at"):
            when = _parse_iso(end["at"])
            if when:
                text = i18n.t(self.lang, "goal_ended", mode=text,
                              time=when.strftime("%m-%d %H:%M"))
        color = "#dc2626" if mode in C.GM_TERMINAL else "#6b7280"
        prefix = i18n.t(self.lang, "goal_label_fmt", name=i18n.t(self.lang, "lbl_goal"))
        self.lbl_goal.configure(text=prefix + text, fg=color)

    def _render_hint(self):
        target = self.cfg.locked_thread
        open_thread = getattr(self, "_open_thread", "")
        if target and open_thread and open_thread != target:
            self.lbl_hint.configure(
                text=i18n.t(self.lang, "hint_locked_not_open", open=open_thread, target=target))
        elif self.banner_text:
            self.lbl_hint.configure(text=self.banner_text)
        else:
            self.lbl_hint.configure(text="")

    def _render_balance(self, bal, quota_reset_at=None):
        """余额显示。

        5 小时的重置时间优先取界面横幅（最新、最准）；百分比只有当天磁盘记录
        与横幅属于同一个窗口时才采用，否则显示「百分比待更新」而不是拿旧窗口的数字。
        """
        self.last_balance = bal or {"ok": False}
        self._quota_reset_at = quota_reset_at
        lang = self.lang
        if not self.last_balance.get("ok"):
            self.lbl_bal_5h.configure(text="—", fg="#6b7280")
            self.lbl_bal_wk.configure(text="—", fg="#6b7280")
            self.lbl_bal_time.configure(text=i18n.t(lang, "bal_unknown"))
            return
        now = datetime.now().astimezone()

        five = self.last_balance.get("five_hour") or {}
        reset_disk = _parse_iso(five.get("resets_at"))
        reset_live = quota_reset_at
        pct5 = five.get("remaining_percent")
        same_window = bool(reset_live and reset_disk and
                           abs((reset_live - reset_disk).total_seconds()) <= 120)
        if reset_live:
            if not same_window:
                pct5 = None          # 旧窗口的百分比不能套到新窗口
        self._set_window(self.lbl_bal_5h, reset_live or reset_disk, pct5, now)

        week = self.last_balance.get("weekly") or {}
        self._set_window(self.lbl_bal_wk, _parse_iso(week.get("resets_at")),
                         week.get("remaining_percent"), now)
        observed = _parse_iso(self.last_balance.get("observed_at"))
        if observed:
            self.lbl_bal_time.configure(
                text=i18n.t(lang, "bal_data_time",
                            time=observed.strftime("%m-%d %H:%M"),
                            ago=self._ago(observed, now)))
        else:
            self.lbl_bal_time.configure(text="")

    def _set_window(self, widget, reset, pct, now):
        """渲染一个额度窗口：百分比 + 重置时间。"""
        lang = self.lang
        if reset and now >= reset:
            widget.configure(text=i18n.t(lang, "bal_window_reset"), fg="#b45309")
            return
        parts = []
        if pct is not None:
            parts.append(i18n.t(lang, "bal_remaining", pct=int(round(pct))))
        else:
            parts.append(i18n.t(lang, "bal_pending"))
        if reset:
            parts.append(i18n.t(lang, "bal_reset_at", time=reset.strftime("%m-%d %H:%M")))
        color = "#111827"
        if pct is None:
            color = "#6b7280"
        elif pct <= 10:
            color = "#dc2626"
        elif pct <= 30:
            color = "#b45309"
        widget.configure(text="  ".join(parts), fg=color)

    def _ago(self, when, now):
        seconds = (now - when).total_seconds()
        if seconds < 60:
            return i18n.t(self.lang, "ago_now")
        if seconds < 3600:
            return i18n.t(self.lang, "ago_minutes", n=int(seconds // 60))
        if seconds < 48 * 3600:
            return i18n.t(self.lang, "ago_hours", n=int(seconds // 3600))
        return i18n.t(self.lang, "ago_days", n=int(seconds // 86400))

    def _tick(self):
        if self.last_reset_at:
            left = int((self.last_reset_at - datetime.now().astimezone()).total_seconds())
            if left > 0:
                h, rem = divmod(left, 3600)
                m, s = divmod(rem, 60)
                self.lbl_reset.configure(
                    text=self.last_reset_at.strftime("%H:%M") + "（" +
                         self.last_reset_at.strftime("%Y-%m-%d %H:%M") + "  " +
                         str(h).zfill(2) + ":" + str(m).zfill(2) + ":" + str(s).zfill(2) + "）")
        self.root.after(1000, self._tick)

    def _summarize(self, rec):
        parts = []
        for key in ("state", "phase", "action", "ok", "detail", "level_detail",
                    "thread", "target", "reset_clock", "read_ms"):
            if key in rec and rec[key] not in ("", None):
                value = rec[key]
                if key == "state":
                    value = i18n.state_text(self.lang, value)
                elif key == "phase":
                    value = i18n.phase_text(self.lang, value)
                parts.append(key + "=" + str(value))
        return " ".join(parts)

    def _append(self, event, text, ts=None, level="info"):
        stamp = ts or datetime.now().astimezone().isoformat(timespec="seconds")
        stamp = stamp[11:19] if len(stamp) >= 19 else stamp
        mark = {"error": "x", "warn": "!", "info": "·"}.get(level, "·")
        self.txt.configure(state="normal")
        self.txt.insert("end", stamp + "  " + mark + " " + event + "  " + text + "\n")
        total = int(self.txt.index("end-1c").split(".")[0]) - 1
        if total > MAX_LOG_LINES:
            self.txt.delete("1.0", str(total - MAX_LOG_LINES + 1) + ".0")
        self.txt.see("end")
        self.txt.configure(state="disabled")
