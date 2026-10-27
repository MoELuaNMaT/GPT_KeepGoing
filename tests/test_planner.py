# -*- coding: utf-8 -*-
"""决策层单元测试：python -m pytest tests -q 或 python tests/test_planner.py"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import constants as C
from app import planner
from app.reader import Snap
from app.config import Config

# 测试隔离：配置写临时目录，绝不碰真实用户配置
import tempfile as _tempfile
import app.config as _cfgmod
_CFG_TMP = _tempfile.mkdtemp(prefix="ar_test_")
_cfgmod.app_dir = lambda: _CFG_TMP


def snap(**kw):
    s = Snap(ok=True)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_priority_running_beats_quota():
    s = snap(stop_present=True, quota_msgs=["额度已用完"], approval=["始终允许"])
    assert planner.classify(s) == C.ST_RUNNING


def test_priority_permission_beats_quota():
    s = snap(approval=["允许一次"], quota_msgs=["额度已用完"])
    assert planner.classify(s) == C.ST_NEEDS_PERMISSION


def test_quota_when_only_banner():
    assert planner.classify(snap(quota_msgs=["使用上限"])) == C.ST_QUOTA


def test_idle():
    assert planner.classify(snap()) == C.ST_IDLE


def test_app_missing():
    assert planner.classify(Snap(ok=False)) == C.ST_APP_MISSING


def test_choose_act_resume_goal():
    s = snap(goal_status=C.GOAL_STALLED, goal_actions=[C.GOAL_RESUME, C.GOAL_CLEAR])
    assert planner.choose_act(s) == "resume_goal"


def test_choose_act_skips_active_goal():
    s = snap(goal_status=C.GOAL_ACTIVE, goal_actions=[C.GOAL_PAUSE])
    assert planner.choose_act(s) == "none"


def test_choose_act_skips_done_goal():
    s = snap(goal_status=C.GOAL_DONE, goal_actions=[C.GOAL_RESUME])
    assert planner.choose_act(s) == "none"


def test_choose_act_send_continue_without_goal():
    assert planner.choose_act(snap()) == "send_continue"


def test_plan_wait_reset():
    now = datetime(2026, 10, 26, 19, 0)
    s = snap(quota_msgs=["于 19:37 重置"], reset_clock="19:37",
             reset_at=datetime(2026, 10, 26, 19, 37))
    r = planner.plan_after_poll(s, C.PHASE_WAIT_RESET, C.ST_QUOTA, now, Config())
    assert r["act"] is False
    assert r["phase"] == C.PHASE_WAIT_RESET
    assert r["due_in"] <= 60


def test_plan_trigger_after_reset_passed():
    now = datetime(2026, 10, 26, 19, 40)
    s = snap(quota_msgs=["于 19:37 重置"], reset_clock="19:37",
             reset_at=datetime(2026, 10, 26, 19, 37))
    r = planner.plan_after_poll(s, C.PHASE_WAIT_RESET, C.ST_QUOTA, now, Config())
    assert r["act"] is True


def test_plan_quota_without_reset():
    now = datetime(2026, 10, 26, 19, 40)
    s = snap(quota_msgs=["或稍后再试"])
    r = planner.plan_after_poll(s, C.PHASE_WAIT_UNKNOWN, C.ST_QUOTA, now, Config())
    assert r["act"] is False
    assert r["phase"] == C.PHASE_WAIT_UNKNOWN


def test_plan_early_recovery():
    now = datetime(2026, 10, 26, 19, 20)
    s = snap()
    r = planner.plan_after_poll(s, C.PHASE_WAIT_RESET, C.ST_QUOTA, now, Config())
    assert r["act"] is True


def test_plan_continue_after_running():
    now = datetime(2026, 10, 26, 19, 20)
    s = snap()
    r = planner.plan_after_poll(s, C.PHASE_MONITOR, C.ST_RUNNING, now, Config())
    assert r["act"] is True


def test_plan_permission_notify():
    now = datetime(2026, 10, 26, 19, 20)
    s = snap(approval=["允许一次"])
    r = planner.plan_after_poll(s, C.PHASE_MONITOR, C.ST_RUNNING, now, Config())
    assert r["act"] is False
    assert r["notify"]


def test_waiting_label_rejects_message_body():
    # 真实误判样本：消息正文里出现了「请选择」
    body = "认证成功后确认：DSH 0.2 使用了新的调用与事件协议，当前仓库不能直接连接。请选择接下来的范围。"
    assert planner.is_waiting_label(body, False) is False


def test_waiting_label_accepts_status_row():
    assert planner.is_waiting_label("正在等待你的回答", False) is True


def test_waiting_label_rejects_offscreen():
    assert planner.is_waiting_label("正在等待你的回答", True) is False


def test_waiting_label_accepts_stamped_variant():
    assert planner.is_waiting_label("正在等待你的回答：请确认范围", False) is True


def test_quota_text_visible():
    assert planner.is_quota_text("你已达到使用上限。升级套餐或充值额度以继续，或稍后再试。", False)


def test_quota_text_offscreen_rejected():
    assert planner.is_quota_text("你已达到使用上限。升级套餐或充值额度以继续，或稍后再试。", True) is False


def test_quota_text_short_rejected():
    assert planner.is_quota_text("额度", False) is False


def test_should_attempt_when_no_quota():
    from datetime import datetime
    now = datetime(2026, 10, 27, 0, 50)
    assert planner.should_attempt(snap(), now) is True


def test_should_not_attempt_when_quota_and_no_reset():
    from datetime import datetime
    now = datetime(2026, 10, 27, 0, 50)
    s = snap(quota_msgs=["或稍后再试"])
    assert planner.should_attempt(s, now, None) is False


def test_should_not_attempt_before_reset():
    from datetime import datetime
    now = datetime(2026, 10, 27, 0, 40)
    s = snap(quota_msgs=["于 00:45 重置"])
    assert planner.should_attempt(s, now, datetime(2026, 10, 27, 0, 45), 90) is False


def test_should_attempt_after_reset_even_with_stale_banner():
    # 真实故障：重置后横幅仍显示用尽，旧逻辑因此放弃点击
    from datetime import datetime
    now = datetime(2026, 10, 27, 0, 46, 32)
    s = snap(quota_msgs=["你已达到使用上限。升级套餐或充值额度以继续，或稍后再试。"])
    assert planner.should_attempt(s, now, datetime(2026, 10, 27, 0, 45), 90) is True


def test_goal_mode_active():
    assert planner.goal_mode(snap(goal_status=C.GOAL_ACTIVE), C.ST_RUNNING) == C.GM_ACTIVE


def test_goal_mode_paused():
    assert planner.goal_mode(snap(goal_status=C.GOAL_PAUSED), C.ST_IDLE) == C.GM_PAUSED


def test_goal_mode_completed():
    assert planner.goal_mode(snap(goal_status=C.GOAL_DONE), C.ST_IDLE) == C.GM_COMPLETED


def test_goal_mode_limited():
    assert planner.goal_mode(snap(goal_status="目标受限"), C.ST_IDLE) == C.GM_LIMITED


def test_stalled_by_quota_is_not_blocked():
    # 昨天 00:45 的真实情况：额度耗尽导致停滞，这种还能救
    assert planner.goal_mode(snap(goal_status=C.GOAL_STALLED), C.ST_QUOTA) == C.GM_BLOCKED_BY_QUOTA


def test_stalled_without_quota_is_blocked():
    assert planner.goal_mode(snap(goal_status=C.GOAL_STALLED), C.ST_IDLE) == C.GM_BLOCKED


def test_goal_mode_none_without_goal():
    assert planner.goal_mode(snap(), C.ST_IDLE) == C.GM_NONE


def test_limited_by_quota_is_resumable():
    # 额度用尽时客户端也会显示「目标受限」，这种等额度回来还能救
    assert planner.goal_mode(snap(goal_status="目标受限"), C.ST_QUOTA) == C.GM_LIMITED_BY_QUOTA


def test_limited_without_quota_stays_limited():
    assert planner.goal_mode(snap(goal_status="目标受限"), C.ST_IDLE) == C.GM_LIMITED


def test_choose_act_resumes_limited_goal():
    s = snap(goal_status="目标受限", goal_actions=[C.GOAL_RESUME, C.GOAL_CLEAR])
    assert planner.choose_act(s) == "resume_goal"


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
    print("---")
    print("total", len(fns), "failed", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
