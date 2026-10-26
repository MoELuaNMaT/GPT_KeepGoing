# 插件版（Plugin Edition）— 可行性调查与方案

状态：调查完成，待决策
更新日期：2026-10-26
关联：`specs/auto-resume.md`（独立应用版）

---

## 1. 问题

现有实现是独立 Windows 应用，靠界面自动化（UIA）读状态、抢焦点、模拟输入。
能否把它改成 ChatGPT / Codex 的插件？

## 2. 结论

**能做，但不能做成"纯插件"。** 正确形态是 **插件外壳 + 本地守候进程**：

- 插件负责：分发安装、应用内入口、暴露工具给模型、管理配置。
- 守候进程负责：等待额度恢复、投递消息。因为额度耗尽时模型本身不工作，
  没有任何插件内代码能在那个时刻被模型驱动。

这条路径不是猜想：这台机器上已经装着一个同类插件（`codex-auto-resume 0.6.18`，已启用），
它就是这个形态。

## 3. 本地实测证据

### 3.1 插件是一等机制

```
codex plugin list / add / remove / marketplace add|list|upgrade|remove
```

插件清单 `.codex-plugin/plugin.json` 字段：`name/version/description/author/license/keywords/skills/mcpServers/interface`。
`interface` 下有 `displayName/shortDescription/longDescription/capabilities/brandColor/composerIcon/logo/screenshots/defaultPrompt`。

### 3.2 插件能带什么

| 能力 | 证据 |
| --- | --- |
| 技能 | `skills/<name>/SKILL.md`（pdf 插件、computer-use 插件都是这个结构） |
| MCP 服务器 | `codex-auto-resume` 的 `"mcpServers": "./.mcp.json"`，内含 stdio 服务器 |
| 原生二进制 | `mcp/codex-auto-resume-mcp.exe`、`codex-computer-use.exe` |
| 脚本 | `scripts/bootstrap.ps1` 等 |

### 3.3 消息投递可以不走界面

```
codex queue --thread <会话 UUID 或名称> --message <文本>
```

已装插件的 README 原文：通过官方 `codex queue` 命令、按会话 UUID 投递，
"never by typing into the Codex window"。

意义：不再需要抢焦点、不再依赖窗口可点、不再受"界面不刷新"影响。

### 3.4 额度重置时间可以精确读到

`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` 每次响应都记录：

```json
{"rate_limits":{"limit_id":"codex",
  "primary":{"used_percent":96.0,"window_minutes":300,"resets_at":1793014647},
  "secondary":{"used_percent":15.0,"window_minutes":10080,"resets_at":1793601447},
  "credits":{"has_credits":false,"balance":"0"},"plan_type":"plus"}}
```

`1793014647` = 2026-10-26T19:37:27+08:00，与当时界面显示的 19:37 完全一致。
另有 `secondary`（周窗口）、`used_percent`、`plan_type`、剩余额度。

意义：不需要"陈旧检测 + 刷新阶梯"，也不需要推算日期。

### 3.5 会话身份可以精确对应

`~/.codex/sqlite/state_5.sqlite` 表 `threads`：
`id`（UUID）、`title`、`cwd`、`rollout_path`、`updated_at`。

意义：可以把界面上的标题映射成 UUID，再交给 `codex queue`，不会串对话。

### 3.6 已有同类插件

`codex-auto-resume@codex-auto-resume-windows 0.6.18  installed, enabled`
本地 marketplace：`C:\Users\乱码碳\.codex-auto-resume\app`
结构：MCP 服务器 + watcher + skill + 设置窗口。

## 4. 三种形态

| 形态 | 做法 | 判断 |
| --- | --- | --- |
| A 纯插件 | 只放 skills + MCP 工具 | **不行**。额度耗尽时模型不动，无人执行 |
| B 插件 + 本地守候进程 | 插件分发与入口，进程等待与投递 | **推荐** |
| C 现状（独立 exe + UIA） | 全走界面自动化 | 可行，但发送脆弱、怕界面不刷新 |

## 5. 插件版相对现版的收益

| 维度 | 现版 | 插件版 |
| --- | --- | --- |
| 发送 | UIA 点击 / 粘贴 / 抢焦点 | `codex queue`，不碰界面 |
| 重置时间 | 界面文本 `HH:MM`，需推算日期 | 会话文件 `resets_at`，精确到秒 |
| 界面不刷新 | 需要刷新阶梯（切会话、重载） | 不读取界面，不受影响 |
| 身份 | 对话标题 | 会话 UUID |
| 安装 | 拷 exe | `codex plugin add` |
| 入口 | 独立窗口 | 应用内「插件」页 + 托盘窗口 |
| 模型可查 | 无 | MCP 工具（查状态、开关、立即续跑） |

## 6. 代价与风险

1. **没有应用内自定义面板**。插件只能提供技能、工具、图标。仪表盘仍是独立窗口。
2. **依赖 CLI 私有行为**。`codex queue` 与 sessions 文件格式不属于稳定公开契约，
   客户端升级可能变化。需要版本探测与降级路径。
3. **`queue` 的可用前提未验证**：会话是否必须在应用中打开、是否需要 app-server 守护进程。
4. **发布渠道**：官方 marketplace 需要审核；自用可加本地或 Git marketplace。
5. **与已装插件功能重叠**，需要决定是复用还是自研。

## 7. 迁移方案

### 第一步（收益最大，风险最低）

不改 UI，只换两条数据通路：

- 发送：UIA → `codex queue --thread <UUID>`；UIA 降级为兜底。
- 额度：界面文本 → sessions `rate_limits`；界面仅用于展示。
- 身份：标题 → `state_5.sqlite.threads` 里的 UUID。

保留现有仪表盘、托盘、开关、日志。

### 第二步：打包成插件

新增目录结构：

```
.codex-plugin/plugin.json     # name/version/skills/mcpServers/interface
.mcp.json                     # stdio MCP 服务器
skills/codex-auto-resume/SKILL.md
mcp/                           # 工具服务器（可复用现有 Python 引擎）
bin/                           # watcher 启动器
assets/icon.png
```

用本地 marketplace 安装：

```
codex plugin marketplace add <本地目录或 Git 仓库>
codex plugin add auto-resume@<marketplace 名>
```

### 第三步：MCP 工具

`get_status` / `list_pending` / `enable` / `disable` /
`retry_now` / `set_policy` / `open_dashboard`

让模型在对话里能直接查询和维护，而不是让用户切窗口。

## 8. 验收标准

| 编号 | 标准 |
| --- | --- |
| P-1 | `codex plugin list` 能看到本插件，状态 installed, enabled |
| P-2 | 应用「插件」页出现条目，图标与描述正确 |
| P-3 | 关闭应用窗口后，守候进程仍能在到点后投递消息 |
| P-4 | 投递后该会话状态变为运行中，且没有抢焦点 |
| P-5 | 重置时间取自 `resets_at`，与界面显示一致 |
| P-6 | 会话被切走不影响投递（按 UUID 定位） |

## 9. 待决策

1. **先评估还是先自研**：机器上已装 `codex-auto-resume 0.6.18`，
   功能与目标高度重合。建议先花 30 分钟实测它，再决定是否自研。
2. **替代还是并存**：插件版是否取代现有 exe。
3. **依赖取舍**：是否接受依赖 `codex queue` 与 sessions 文件格式。
4. **发布方式**：仅自用（本地 marketplace）还是公开（Git marketplace / 官方审核）。

## 附录：本次调查用到的命令

```
codex plugin list
codex plugin marketplace list
codex queue --help
codex mcp list
```
