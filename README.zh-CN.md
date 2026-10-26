# GPT KeepGoing

**给 ChatGPT Windows 桌面客户端的自动继续工具。**

[English](README.md) | 简体中文

---

## 它解决什么问题

你把一个长任务丢给 ChatGPT 桌面客户端，它跑到一半撞上用量上限，告诉你「00:45 后再试」。
00:45 的时候你在睡觉。第二天早上，任务还停在原地。

客户端自己不会解决这个问题，原因有两条：

1. **窗口在后台时它不刷新额度。** 我们做过实测：9 分钟、24 次采样，跨过重置时刻，
   横幅从头到尾没变过。
2. **就算刷新了，也还得有人去点「恢复目标」或打一句「继续」。**

## 它做什么

GPT KeepGoing 是一个 Windows 托盘小工具。它盯住一个对话，替你把「继续」按下去。

- **自动找客户端。** 不需要配置，不依赖窗口标题。
- **每分钟检查一次。** 从客户端的无障碍树读状态，不打扰窗口。
- **优先走目标。**
  - 对话里有目标 → 点「恢复目标」，弹出确认框就再点「继续目标」。
  - 没有目标 → 往输入框写入一句话并发送。
- **任务结束后也会继续**，不只是额度恢复。
- **多语言。** 7 种界面语言，发给对话的那句话也跟着换。
- **显示额度。** 5 小时与每周两个窗口，含重置时间。
- **不碍事。** 托盘图标、可选开机自启、20 行日志，只在真需要你时才通知。

不改账号、不调 API、不改客户端。

## 多语言

界面和发送的话都跟随所选语言。语言名一律用该语言自己的文字书写。

| 语言 | 界面 | 发送的内容 |
| --- | --- | --- |
| 简体中文 | 自动续跑助手 | 继续 |
| English | Auto Resume | Continue |
| 日本語 | 自動再開アシスタント | 続けて |
| 한국어 | 자동 재개 도우미 | 계속 진행해 |
| Deutsch | Auto-Fortsetzen | Weiter |
| Français | Reprise automatique | Continue |
| Italiano | Ripresa automatica | Continua |

## 它怎么判断

| 读到的状态 | 它会做什么 |
| --- | --- |
| 运行中 | 等待。任务结束后继续。 |
| 额度用尽，有重置时间 | 睡到重置时刻，再继续。 |
| 额度用尽，无重置时间 | 每分钟检查，直到额度恢复。 |
| 等权限审批 | **什么都不做**，只发通知。 |
| 等你回复 | **什么都不做**，只发通知。 |
| 空闲 | 等待。 |

它不会替你批准权限，也不会在输入框已有草稿时发送。

## 环境要求

- Windows 10 或 11
- 已安装并登录 ChatGPT 桌面客户端（包名 `OpenAI.Codex`）
- 不需要管理员权限，除非客户端本身以管理员运行

实测客户端版本 `26.1013.4894.0`。

## 怎么跑起来

### 从源码运行

```bat
pip install uiautomation psutil pystray pillow
python main.py
```

### 打成单个 exe

```bat
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name AutoResume --collect-all comtypes --collect-all pystray ^
  --hidden-import comtypes.gen main.py
```

产物是 `dist\AutoResume.exe`，约 37 MB，不需要装 Python。

## 怎么用

1. 启动后，界面会显示当前打开的那个对话。
2. 选**目标对话**：从下拉列表里选，或直接点「用当前」。
3. 打开**自动继续**。会弹一个确认框，说明它会：
   把窗口拉到前台，并短暂切到别的对话再切回来，强制客户端刷新。
   能接受再确认。
4. 让它挂着。它每分钟检查一次。

关窗口是收进托盘，不是退出。要退出走托盘菜单。

## 界面上能看到什么

- **目标对话**及其所属项目
- **当前状态**（大白话）
- **额度重置**时间，取自客户端横幅
- **额度**：5 小时与每周的剩余百分比、重置时间、数据距今多久
- **最近 20 条日志**，带时间

## 需要说清楚的限制

- **客户端不暴露实时百分比。** 百分比来自客户端自己的本地会话记录，而记录只在一次
  回合结束时才写入。当记录的窗口与横幅的窗口对不上时，界面显示「百分比待更新」，
  而不是拿旧数字糊弄你。
- **界面自动化依赖客户端的文案。** 客户端改版把按钮改名，识别就会失效。
  相关字符串集中在 `app/constants.py` 与 `app/i18n.py`。
- **一次只盯一个对话。** 同时盯多个就得每分钟切换会话，太打扰。
- **与 OpenAI 无关。** 这是第三方自动化工具。

## 它是怎么做到的

| 层面 | 用了什么 |
| --- | --- |
| 找客户端 | Win32 `EnumWindows` + 进程名 |
| 读状态 | Windows UI Automation，读 Chromium 无障碍树 |
| 发送 | UIA Invoke、剪贴板粘贴、键盘事件 |
| 额度数字 | 只读解析 `%USERPROFILE%\.codex\sessions\**\rollout-*.jsonl` |
| 调度 | 后台线程 + 状态机 |

不联网、不上报。配置与日志在 `%LOCALAPPDATA%\AutoResume\`。

## 开发

```
main.py              入口：单实例、托盘、界面、调度线程
app/discovery.py     找窗口（Win32）、拉前台
app/reader.py        用 UIA 读一次快照
app/planner.py       纯决策函数
app/actor.py         刷新阶梯、切对话、恢复目标、发送
app/engine.py        后台调度线程与状态机
app/ratelimit.py     从本地会话记录读 5 小时与每周余额
app/i18n.py          7 种语言
app/tray.py          托盘图标与菜单
app/autostart.py     开机自启注册表项
app/notify.py        托盘气泡通知
app/ui.py            tkinter 仪表盘
```

测试共 40 个用例，不需要界面：

```bat
python tests\test_planner.py
python tests\test_engine.py
python tests\test_i18n.py
```

设计说明在 `specs/auto-resume.md`。
