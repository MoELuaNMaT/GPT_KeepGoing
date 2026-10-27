# -*- coding: utf-8 -*-
"""引擎层测试：用假快照驱动一次轮询，不碰真实界面。"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.engine as engmod
from app import constants as C
from app.config import Config
from app.reader import Snap

# 测试隔离：配置写临时目录，绝不碰真实用户配置
import tempfile as _tempfile
import app.config as _cfgmod
_CFG_TMP = _tempfile.mkdtemp(prefix="ar_test_")
_cfgmod.app_dir = lambda: _CFG_TMP


class FakeLog:
    def __init__(self):
        self.records = []

    def write(self, level, event, **kw):
        self.records.append((level, event, kw))
        return {"level": level, "event": event}


def make_engine(cfg, snaps, act_result=None):
    """构造引擎并替换读取器与动作层。"""
    calls = {"read": 0, "act": 0}

    def fake_read(win=None):
        calls["read"] += 1
        return snaps[min(calls["read"] - 1, len(snaps) - 1)]

    def fake_act(cfg_, log_, **kwargs):
        calls["act"] += 1
        calls["expect_reset_at"] = kwargs.get("expect_reset_at")
        calls["force"] = kwargs.get("force")
        return act_result or {"ok": True, "action": "resume_goal", "detail": "stub"}

    engmod.reader.read = fake_read
    engmod.actor.run_act = fake_act
    cfg.auto_resume = True
    engine = engmod.Engine(cfg, FakeLog(), lambda p: None, None)
    engine.enabled = True
    return engine, calls


def test_target_not_open_blocks_state():
    cfg = Config()
    cfg.locked_project = "P"
    cfg.locked_thread = "A"
    engine, calls = make_engine(cfg, [Snap(ok=True, project="P", thread="B", stop_present=True)])
    engine._cycle()
    assert engine.phase == C.PHASE_LOCKED_NOT_OPEN
    assert calls["act"] == 0                 # 绝不动作
    assert engine.cfg.locked_thread == "A"   # 目标不变


def test_follow_mode_switches_target():
    cfg = Config()
    cfg.locked_project = "P"
    cfg.locked_thread = "A"
    cfg.follow_open_thread = True
    engine, _ = make_engine(cfg, [Snap(ok=True, project="P2", thread="B")])
    engine._cycle()
    assert engine.cfg.locked_thread == "B"
    assert engine.cfg.locked_project == "P2"


def test_manual_act_bypasses_plan():
    cfg = Config()
    cfg.locked_project = "P"
    cfg.locked_thread = "A"
    engine, calls = make_engine(cfg, [Snap(ok=True, project="P", thread="A", stop_present=True)])
    engine.request_act_now()
    engine._cycle()
    assert calls["act"] == 1                  # 即使处于运行中也执行一次
    assert engine.attempts == 0               # 手动不计数


def test_failed_manual_does_not_halt():
    cfg = Config()
    cfg.locked_project = "P"
    cfg.locked_thread = "A"
    engine, _ = make_engine(
        cfg, [Snap(ok=True, project="P", thread="A")],
        act_result={"ok": False, "action": "none", "detail": "stub fail"})
    engine.request_act_now()
    engine._cycle()
    assert engine.attempts == 0
    assert engine.halted is False


def test_auto_failure_counts_and_halts():
    cfg = Config()
    cfg.locked_project = "P"
    cfg.locked_thread = "A"
    cfg.retry_window_minutes = 2
    snap = Snap(ok=True, project="P", thread="A")
    engine, _ = make_engine(cfg, [snap], act_result={"ok": False, "action": "none", "detail": "x"})
    engine._manual = False
    engine.phase = C.PHASE_ACT
    engine._execute(manual=False)
    assert engine.attempts == 1
    engine._execute(manual=False)
    assert engine.halted is True
    assert engine.phase == C.PHASE_NEEDS_HUMAN


def test_completed_goal_stops_monitoring():
    cfg = Config()
    cfg.locked_project = "P"
    cfg.locked_thread = "A"
    engine, calls = make_engine(cfg, [Snap(ok=True, project="P", thread="A",
                                           goal_status="已达成目标")])
    engine._cycle()
    assert calls["act"] == 0            # 绝不点恢复
    assert engine.enabled is False      # 结束监控
    assert engine.goal_end["mode"] == "completed"
    assert engine.goal_end["at"]        # 记录了时间


def test_blocked_goal_stops_monitoring():
    cfg = Config()
    cfg.locked_project = "P"
    cfg.locked_thread = "A"
    engine, calls = make_engine(cfg, [Snap(ok=True, project="P", thread="A",
                                           goal_status="目标已停滞")])
    engine._cycle()
    assert calls["act"] == 0
    assert engine.enabled is False
    assert engine.goal_end["mode"] == "blocked"


def test_stalled_by_quota_keeps_monitoring():
    # 额度导致的停滞不算阻塞，必须继续等额度
    cfg = Config()
    cfg.locked_project = "P"
    cfg.locked_thread = "A"
    engine, _ = make_engine(cfg, [Snap(ok=True, project="P", thread="A",
                                       goal_status="目标已停滞",
                                       quota_msgs=["你已达到使用上限。稍后再试"])])
    engine._cycle()
    assert engine.enabled is True
    assert engine.goal_end is None


def test_limited_by_quota_keeps_monitoring():
    cfg = Config()
    cfg.locked_project = "P"
    cfg.locked_thread = "A"
    engine, calls = make_engine(cfg, [Snap(ok=True, project="P", thread="A",
                                           goal_status="目标受限",
                                           quota_msgs=["你已达到使用上限。稍后再试"])])
    engine._cycle()
    assert engine.enabled is True       # 没结束监控
    assert calls["act"] == 0            # 额度没恢复前不动作
    assert engine.goal_end is None      # 不算终态


def test_limited_without_quota_notifies_only():
    cfg = Config()
    cfg.locked_project = "P"
    cfg.locked_thread = "A"
    engine, calls = make_engine(cfg, [Snap(ok=True, project="P", thread="A",
                                           goal_status="目标受限")])
    engine._cycle()
    assert calls["act"] == 0            # 不替用户点恢复
    assert engine.enabled is True       # 但继续监控
    assert engine.goal_end is None


def run():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print("PASS", name)
        except AssertionError as exc:
            failed += 1
            print("FAIL", name, exc)
        except Exception as exc:
            failed += 1
            print("ERROR", name, repr(exc))
    print("---")
    print("total", len(fns), "failed", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
