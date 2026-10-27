# GPT KeepGoing

**Auto-continue for the ChatGPT Windows desktop app.**

English | [简体中文](README.zh-CN.md)

---

## The problem

You leave a long task running in the ChatGPT desktop app. It stops because you hit the
usage limit, and tells you to try again at 00:45. Nobody is awake at 00:45. In the
morning the task is exactly where it stopped.

The app will not fix this by itself, because:

1. It does not refresh its quota while the window is in the background. We measured
   24 samples over 9 minutes across a reset point: the banner never changed.
2. Even when it refreshes, someone still has to click **Resume goal** or type
   "continue".

## What this does

GPT KeepGoing is a small Windows tray app. It watches one conversation and continues
it for you.

- **Finds the client automatically.** No configuration, no window title matching.
- **Checks every minute.** Reads the state from the client's accessibility tree.
- **Continues the right way — goal first.**
  - If the conversation has a goal, it clicks **Resume goal**, and confirms the
    follow-up dialog if one appears.
  - If there is no goal, it types a continuation message and sends it.
- **Continues after a finished task**, not only after a quota reset.
- **Speaks your language.** 7 UI languages, and the sent message is localized too.
- **Shows your quota.** 5-hour and weekly windows, with reset times.
- **Stays out of the way.** Tray icon, optional autostart, a 20-line log, and
  notifications only when you are actually needed.

It never touches your account, never calls an API, and never modifies the client.

## Languages

The interface and the continuation message both follow the selected language.
Language names are always written in their own script.

| Language | Interface | Message sent |
| --- | --- | --- |
| 简体中文 | 自动续跑助手 | 继续 |
| English | Auto Resume | Continue |
| 日本語 | 自動再開アシスタント | 続けて |
| 한국어 | 자동 재개 도우미 | 계속 진행해 |
| Deutsch | Auto-Fortsetzen | Weiter |
| Français | Reprise automatique | Continue |
| Italiano | Ripresa automatica | Continua |

## How it decides

| State it reads | What it does |
| --- | --- |
| Running | Waits. Continues when the task ends. |
| Quota exhausted, reset time known | Sleeps until the reset time, then continues. |
| Quota exhausted, no reset time | Checks every minute until quota returns. |
| Reset time passed, banner still says exhausted | Still tries to continue, then checks whether the task actually started. The banner is known to lag. |
| Waiting for permission | **Does nothing.** Sends a notification instead. |
| Waiting for your reply | **Does nothing.** Sends a notification instead. |
| Idle | Waits. |
| Goal paused, or stalled by the quota | Continues when the limit resets or the task ends. |
| Goal completed | Records the time, notifies you, and turns itself off. |
| Goal blocked | Confirmed over 3 checks before it turns itself off. If a reset time is still pending it keeps waiting and tries Resume once at that time. |

The app never approves a permission request for you, and never sends a message when
the composer already has a draft.

## Requirements

- Windows 10 or 11
- The ChatGPT desktop app (package `OpenAI.Codex`) installed and signed in
- No administrator rights, unless the client itself runs elevated

Tested against client build `26.1013.4894.0`.

## Run it

### From source

```bat
pip install uiautomation psutil pystray pillow
python main.py
```

### Build a single exe

```bat
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name AutoResume --collect-all comtypes --collect-all pystray ^
  --hidden-import comtypes.gen main.py
```

The result is `dist\AutoResume.exe`, about 37 MB, no Python required.

## Using it

1. Start the app. It shows the conversation that is currently open.
2. Pick a **target conversation**, either from the dropdown or with **Use current**.
3. Turn on **Auto continue**. A dialog explains what will happen:
   the app must bring the window to the front and briefly switch conversations to
   force the client to refresh. Confirm only if that is acceptable.
4. Leave it running. It checks every minute.

Closing the window sends it to the tray. Use the tray menu to reopen it or to quit.

## What it shows

- **Target conversation** and the project it belongs to.
- **Current state** in plain words.
- **Limit reset** time, taken from the client banner.
- **Quota**: 5-hour and weekly, with remaining percentage, reset time, and how old
  the data is.
- **Last 20 log lines**, with timestamps.

## Honest limitations

- **The client does not expose a live quota percentage.** Percentages come from the
  client's own local session records, which are only written when a turn finishes.
  When the recorded window no longer matches the banner, the app says
  "percentage pending" rather than showing a stale number.
- **UI automation depends on the client's wording.** A client update that renames a
  button can break detection. The strings are centralised in
  `app/constants.py` and `app/i18n.py`.
- **One conversation at a time.** Watching several would mean switching threads every
  minute, which is disruptive.
- **Not affiliated with OpenAI.** This is a third-party automation tool.

## How it works

| Layer | What it uses |
| --- | --- |
| Finding the client | Win32 `EnumWindows` + process name |
| Reading state | Windows UI Automation on the Chromium accessibility tree |
| Sending | UI Automation invoke, clipboard paste, and keystrokes |
| Quota numbers | Read-only parsing of `%USERPROFILE%\.codex\sessions\**\rollout-*.jsonl` |
| Scheduling | A background thread with a state machine |

No network access. No telemetry. Configuration and logs live in
`%LOCALAPPDATA%\AutoResume\`.

## Development

```
main.py              entry point: single instance, tray, UI, scheduler
app/discovery.py     find the window (Win32), bring it to the front
app/reader.py        read a state snapshot via UIA
app/planner.py       pure decision functions
app/actor.py         refresh ladder, switch thread, resume goal, send message
app/engine.py        background scheduler and state machine
app/ratelimit.py     read 5-hour and weekly quota from local session records
app/i18n.py          7 languages
app/tray.py          tray icon and menu
app/autostart.py     HKCU Run entry
app/notify.py        tray balloon notifications
app/ui.py            tkinter dashboard
```

Tests (40 cases, no GUI required):

```bat
python tests\test_planner.py
python tests\test_engine.py
python tests\test_i18n.py
```

Design notes live in `specs/auto-resume.md`.
