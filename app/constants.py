# -*- coding: utf-8 -*-
"""界面标签、状态枚举与阈值常量。

这些字符串来自客户端自带的中文语言包，改动客户端版本后需要复核。
"""

# 客户端进程与窗口类
PROCESS_NAME = "ChatGPT.exe"
WINDOW_CLASS = "Chrome_WidgetWin_1"

# 运行中：出现停止按钮即为运行中
STOP_LABELS = ("停止生成", "停止响应", "停止", "Stop generating", "Stop",
               "Stoppen", "Generatie stoppen")

# 需要用户给权限：审批卡按钮
APPROVAL_LABELS = ("允许一次", "允许此对话", "始终允许", "拒绝", "审批选项",
                   "Allow", "Always allow", "Deny",
                   "Eenmalig toestaan", "Toestaan in dit gesprek", "Altijd toestaan",
                   "Weigeren", "Goedkeuringsopties")

# 需要用户回复：客户端「代理活动」里的状态行，必须精确匹配整句。
# 不能用包含匹配，否则消息正文里出现「请选择」之类的词就会误判。
# tuple：str.startswith 接受元组
WAITING_TEXT = ("正在等待你的回答", "Wachten op je antwoord")

# 额度用尽
QUOTA_HINTS = ("额度已用完", "使用上限", "usage limit", "rate limit",
               "je gebruikslimiet bereikt")

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
GM_LIMITED_BY_QUOTA = "limited_by_quota"
# 这两种不再自动推进：记录时间、通知、结束监控
GM_TERMINAL = (GM_BLOCKED, GM_COMPLETED)
# 只通知、不动作，但继续监控（非额度造成的受限，不该替用户点恢复）
GM_NOTIFY_ONLY = (GM_LIMITED,)

# 目标动作按钮
GOAL_RESUME = "恢复目标"
GOAL_PAUSE = "暂停目标"
GOAL_CLEAR = "清除目标"
GOAL_EDIT = "编辑目标"
GOAL_RESUME_CONFIRM = "继续目标"

# Nederlandse client (OpenAI.Codex 26.1106): label -> canonieke constante hierboven.
# De rest van de code rekent alleen met de canonieke waarden.
NL_ALIASES = {
    "Het doel is vastgelopen": GOAL_STALLED,
    "Doel nastreven": GOAL_ACTIVE,
    "Gepauzeerd doel": GOAL_PAUSED,
    "Doel bereikt": GOAL_DONE,
    "Doel beperkt": GOAL_LIMITED[0],
    "Beperkt doelgebruik": GOAL_LIMITED[2],
    "Doel hervatten": GOAL_RESUME,
    "Doel pauzeren": GOAL_PAUSE,
    "Doel wissen": GOAL_CLEAR,
    "Doel bewerken": GOAL_EDIT,
}


def canon(name):
    """Nederlands label omzetten naar de canonieke (Chinese) waarde."""
    return NL_ALIASES.get(name, name)


GOAL_RESUME_NAMES = (GOAL_RESUME, GOAL_RESUME_CONFIRM, "Doel hervatten")
GOAL_RESUME_CONFIRM_NAMES = (GOAL_RESUME_CONFIRM, "Doel hervatten")
NEW_CHAT_NAMES = ("新聊天", "Nieuwe chat")
PERMISSION_BUTTON_NAMES = ("更改权限", "Machtigingen wijzigen")
# 侧边栏项目列表：中文是「X中的已安排任务」，荷兰语是「Geplande taken in X」
TASKS_LIST_SUFFIX = "中的已安排任务"
TASKS_LIST_PREFIX_NL = "Geplande taken in "

# 输入区
# 周额度用尽弹窗（codex.rateLimitResetPurchaseModal）：只点「使用已有的重置」，
# 绝不点付费按钮。按钮只在确实有可用重置时才出现。
BANKED_RESET_LABELS = ("Beschikbare reset gebruiken", "Use available reset", "使用可用重置次数")
# 用量弹窗里的重置列表（codex.rateLimitResetPromptModal）：两步，先「使用」再「确认」
RESET_LIST_TOGGLE_LABELS = ("Resetmomenten gebruikslimiet", "Usage limit resets", "使用限额重置")
USE_RESET_LABELS = ("Resetten gebruiken", "Use reset", "使用重置")
CONFIRM_RESET_LABELS = ("Bevestigen", "Confirm", "确认")
# 名字里含这些词的按钮一律不点（付费购买）
PURCHASE_MARKERS = ("Betaal", "betaal", "Pay ", "pay ", "Buy", "kopen", "Kopen",
                    "Upgrade", "upgrade", "Credits", "credits", "支付", "购买", "升级")
RESET_DONE_TEXTS = ("De gebruikslimieten zijn gereset", "Gebruikslimieten zijn gereset",
                    "Gebruikslimieten gereset",
                    "Usage limits reset", "额度限制已重置", "使用限额已重置")
# Instellingen > Gebruik en facturering > Resetmomenten voor gebruikslimiet
# (settings.usage.resets.*). Alleen de Nederlandse labels zijn live gezien.
SETTINGS_DOC_NAMES = ("Instellingen", "Settings", "设置")
USAGE_SETTINGS_LABELS = ("Gebruik en facturering", "Usage and billing", "Usage & billing")
SETTINGS_USE_RESET_LABELS = ("Resetmoment gebruiken", "Use reset")
NO_RESETS_TEXTS = ("Geen resetmomenten beschikbaar", "No resets available")
# Resetsoorten die ook de weeklimiet herstellen
WEEKLY_RESET_MARKERS = ("wekelijks", "Wekelijks", "weekly", "Weekly", "Volledig", "Full")
BACK_LABELS = ("Terug", "Back", "返回")

# 等待超过这个时长，只可能是周额度
WEEKLY_MIN_WAIT_HOURS = 6

SEND_LABELS = ("发送", "发送消息", "Bericht verzenden", "Verzenden")
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
