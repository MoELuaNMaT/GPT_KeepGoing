# -*- coding: utf-8 -*-
"""界面标签、状态枚举与阈值常量。

这些字符串来自客户端自带的中文语言包，改动客户端版本后需要复核。
"""

# 客户端进程与窗口类
PROCESS_NAME = "ChatGPT.exe"
WINDOW_CLASS = "Chrome_WidgetWin_1"

# 运行中：出现停止按钮即为运行中
STOP_LABELS = ("停止生成", "停止响应", "停止", "Stop generating", "Stop")

# 需要用户给权限：审批卡按钮
APPROVAL_LABELS = ("允许一次", "允许此对话", "始终允许", "拒绝", "审批选项",
                   "Allow", "Always allow", "Deny")

# 需要用户回复：客户端「代理活动」里的状态行，必须精确匹配整句。
# 不能用包含匹配，否则消息正文里出现「请选择」之类的词就会误判。
WAITING_TEXT = "正在等待你的回答"

# 额度用尽
QUOTA_HINTS = ("额度已用完", "使用上限", "usage limit", "rate limit")

# 目标状态文案（composer.threadGoal.summary.*）
GOAL_STALLED = "目标已停滞"
GOAL_ACTIVE = "进行中的目标"
GOAL_PAUSED = "已暂停的目标"
GOAL_DONE = "已达成目标"
GOAL_LIMITED = ("目标受限", "目标使用限制", "目标使用受限")
GOAL_LABELS = (GOAL_STALLED, GOAL_ACTIVE, GOAL_PAUSED, GOAL_DONE) + GOAL_LIMITED

# 目标模式（归一后的语义）
GM_NONE = "none"
GM_ACTIVE = "active"
GM_PAUSED = "paused"
GM_BLOCKED = "blocked"
GM_COMPLETED = "completed"
GM_LIMITED = "limited"
GM_BLOCKED_BY_QUOTA = "blocked_by_quota"
# 这两种不再自动推进：记录时间、通知、结束监控
GM_TERMINAL = (GM_BLOCKED, GM_COMPLETED)

# 目标动作按钮
GOAL_RESUME = "恢复目标"
GOAL_PAUSE = "暂停目标"
GOAL_CLEAR = "清除目标"
GOAL_EDIT = "编辑目标"
GOAL_RESUME_CONFIRM = "继续目标"

# 输入区
SEND_LABELS = ("发送", "发送消息")
COMPOSER_CLASS_MARK = "ProseMirror"

# 状态枚举
ST_APP_MISSING = "app_missing"
ST_RUNNING = "running"
ST_NEEDS_PERMISSION = "needs_permission"
ST_NEEDS_REPLY = "needs_reply"
ST_QUOTA = "quota_exhausted"
ST_IDLE = "idle"
ST_LOCKED_MISSING = "locked_thread_missing"
ST_LOCKED_NOT_OPEN = "locked_thread_not_open"



# 运行阶段。这些是内部码，界面文案由 i18n 翻译
PHASE_OFF = "off"
PHASE_MONITOR = "monitor"
PHASE_WAIT_RESET = "wait_reset"
PHASE_WAIT_UNKNOWN = "wait_unknown"
PHASE_REFRESH = "refresh"
PHASE_ACT = "act"
PHASE_COOLDOWN = "cooldown"
PHASE_NEEDS_HUMAN = "needs_human"
PHASE_APP_MISSING = "app_missing"
PHASE_LOCKED_NOT_OPEN = "locked_not_open"
