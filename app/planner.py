# -*- coding: utf-8 -*-
"""纯决策函数。不碰界面，只吃快照和配置，方便单测。"""

from . import constants as C


def is_waiting_label(name, offscreen=False):
    """是否是「等待你回答」的活动状态行。

    必须精确以该句开头，且当前可见。消息正文里出现同样的词不算。
    """
    text = (name or "").strip()
    if not text or offscreen:
        return False
    return text.startswith(C.WAITING_TEXT)


def is_quota_text(name, offscreen=False):
    """是否是额度横幅文案。必须当前可见。

    残余风险：对话正文里可见地引用了同样的横幅语句时，仍可能被当成横幅。
    """
    text = (name or "").strip()
    if not text or offscreen or len(text) <= 8:
        return False
    return any(hint in text for hint in C.QUOTA_HINTS)


def classify(snap):
    """把快照归类成状态。优先级：运行中 > 待授权 > 待回复 > 额度满 > 空闲。"""
    if not snap.ok:
        return C.ST_APP_MISSING
    if snap.stop_present:
        return C.ST_RUNNING
    if snap.approval:
        return C.ST_NEEDS_PERMISSION
    if snap.waiting_text:
        return C.ST_NEEDS_REPLY
    if snap.quota_msgs:
        return C.ST_QUOTA
    return C.ST_IDLE


def choose_act(snap):
    """决定怎么继续。返回 resume_goal / send_continue / none。"""
    status = snap.goal_status
    if status == C.GOAL_ACTIVE:
        return "none"                      # 已经在跑
    if status == C.GOAL_DONE:
        return "none"                      # 已达成，不再点
    if status == C.GOAL_PAUSED:
        if C.GOAL_RESUME in snap.goal_actions:
            return "resume_goal"
        return "none"
    if status == C.GOAL_STALLED:
        # 停在额度上的停滞可以救；其它情况属于 blocked，由引擎拦下，不点
        return "resume_goal" if C.GOAL_RESUME in snap.goal_actions else "none"
    if status in C.GOAL_LABELS:
        return "none"                      # 目标受限等，不擅自恢复
    return "send_continue"                 # 没有目标


def goal_mode(snap, state):
    """把客户端的目标文案归一成语义模式。

    关键区分：因额度用尽而停滞的目标，不算 blocked。它还能救，等额度回来点恢复。
    只有在额度正常、对话空闲时仍停滞，才算 agent 自己放弃了。
    """
    status = snap.goal_status
    if not status:
        return C.GM_NONE
    if status == C.GOAL_ACTIVE:
        return C.GM_ACTIVE
    if status == C.GOAL_PAUSED:
        return C.GM_PAUSED
    if status == C.GOAL_DONE:
        return C.GM_COMPLETED
    if status in C.GOAL_LIMITED:
        return C.GM_LIMITED
    if status == C.GOAL_STALLED:
        return C.GM_BLOCKED_BY_QUOTA if state == C.ST_QUOTA else C.GM_BLOCKED
    return C.GM_NONE


def should_attempt(snap, now, expect_reset_at=None, grace_seconds=0):
    """过了重置时刻是否值得尝试一次继续。

    横幅已知会滞留：重置后它可能还写着「额度已用完」。所以只要过了重置时刻，
    就不能因为横幅而放弃；真正的判据是动作之后状态有没有变成运行中。
    """
    if not snap.quota_msgs:
        return True
    if expect_reset_at is None:
        return False
    return now >= expect_reset_at + _seconds(grace_seconds)


def is_stale(snap, now, cfg):
    """界面可能没刷新：已过重置时刻但界面仍显示额度用尽。"""
    if not snap.quota_msgs:
        return False
    if not snap.reset_at:
        return False
    return now >= snap.reset_at + _seconds(cfg.stale_grace_seconds)


def plan_after_poll(snap, phase, prev_state, now, cfg):
    """轮询后该怎么走。

    返回 dict：
      phase    下一阶段（用于界面显示）
      due_in   距下次动作的秒数
      act      是否立刻执行继续
      notify   需要发的通知文案，没有则 None
      reason   写进日志的原因
    """
    state = classify(snap)
    poll = cfg.poll_seconds

    if state == C.ST_APP_MISSING:
        return _r(C.PHASE_APP_MISSING, 10, False, None, "客户端未运行")

    if state == C.ST_RUNNING:
        return _r(C.PHASE_MONITOR, poll, False, None, "任务运行中")

    if state == C.ST_NEEDS_PERMISSION:
        return _r(C.PHASE_NEEDS_HUMAN, poll, False,
                  "needs_permission", "等待权限")

    if state == C.ST_NEEDS_REPLY:
        return _r(C.PHASE_NEEDS_HUMAN, poll, False,
                  "needs_reply", "等待回复")

    if state == C.ST_QUOTA:
        if snap.reset_at:
            remaining = (snap.reset_at + _seconds(cfg.stale_grace_seconds) - now).total_seconds()
            if remaining <= 0:
                return _r(C.PHASE_REFRESH, 0, True, None, "已过重置时刻，开始重试")
            if is_stale(snap, now, cfg):
                return _r(C.PHASE_REFRESH, 0, True, None, "界面疑似陈旧")
            return _r(C.PHASE_WAIT_RESET, min(poll, remaining), False, None,
                      "额度用尽，等待 " + snap.reset_clock)
        return _r(C.PHASE_WAIT_UNKNOWN, poll, False, None, "额度用尽，且无重置时间")

    # 空闲
    if phase in (C.PHASE_WAIT_RESET, C.PHASE_WAIT_UNKNOWN) or prev_state == C.ST_RUNNING:
        return _r(C.PHASE_ACT, 0, True, None, "额度已恢复或任务已结束，执行继续")

    return _r(C.PHASE_MONITOR, poll, False, None, "空闲")


def _r(phase, due_in, act, notify, reason):
    return {"phase": phase, "due_in": due_in, "act": act,
            "notify": notify, "reason": reason}


def _seconds(n):
    from datetime import timedelta
    return timedelta(seconds=int(n))
