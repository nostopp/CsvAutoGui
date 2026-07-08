# 核心规则

## 适用范围

这个 skill 面向当前工作区中的 CsvAutoGui 仓库。
仓库级结构和运行时行为摘要见 `AGENTS.md`。

当你需要更广义的仓库上下文时，去读 `AGENTS.md`。
这个文件只保留和配置编写直接相关的规则。

## 需要尊重的运行时事实

- CSV 列名使用 `csv_schema.py` 中定义的中文列名。
- `main.csv` 是默认入口流程。
- `recovery.csv` 是可选的 config 级恢复流程。
- 普通 `.csv` 文件可以作为子流程。
- `runtime.json` 是可选的 config 级运行参数文件，用于配置 `watchdog`、stall 未解决通知和 `notify` 节点通知通道。
- 运行时 `*_resource.csv` 是给脚本用的，不是普通流程控制文件。
- CSV、脚本模块和运行时资源文件都有缓存，修改后需要手动重载。

`watchdog` 是否启用由 `runtime.json.watchdog.mode` 决定：

- `off`：关闭
- `on`：启用
- `auto`：当前 config 有 `recovery.csv`，或 `on_stall_unresolved.remote_notify=true` 时启用

如果启用了 `watchdog` 且当前 config 存在 `recovery.csv`：

- 主流程 stall 后会执行 `recovery.csv`
- `recovery.csv` 正常结束后，整个 config 会从 `main.csv` 重新开始
- 重启前会清空共享 `state`

如果 stall 后无法自动闭环：

- 运行时会进入 `on_stall_unresolved`
- 可按配置做本地通知或远程通知
- 当前实例随后终止

`runtime.json` 的字段回落规则是：

- 主流程：`watchdog -> 默认值`
- 恢复流程：`watchdog.recovery_watchdog -> watchdog -> 默认值`

`recovery_limit` 只属于 `watchdog`，且小于 0 表示不限制恢复次数。

通知相关约定：

- `notification.notify_operation` 控制普通 `notify` 节点的默认通知通道
- `notification.remote` 控制远程通知能力
- 远程 sendkey 可直接写 `sendkey`，也可改用 `sendkey_env`

## 编写时需要关注的节点语义

- 没有分支参数的 `pic` 和 `ocr` 会持续重试直到命中，然后把鼠标移动到目标中心。
- 带 `exist/notExist` 的 `pic` 和 `ocr` 本质上是控制流节点。
- `jmp` 可以接受序号或跳转标记。
- `script` 适合纯 CSV 控制流已经太脆弱或太重复的情况。
- `resource` 节点不能出现在普通流程文件中。
- `notify` 是否只做本地通知，还是同时远程推送，由 `runtime.json` 决定。

在启用 `watchdog` 的配置里：

- 鼠标点击、按键、输入等真实外部输入会被视为有效操作
- 观察、判断、跳转和提示不会被视为有效操作
- 脚本里的 `ctx.input` 会参与有效操作统计
- 脚本里的 `ctx.find_*` 会参与观察统计

## 编写阶段资源清单

这个 skill 使用 `<config_name>_resource.csv` 作为编写阶段的资源清单。

这个文件的定位是：

- 在流程确认后创建
- 由 skill 预填需要的 `pic/ocr` 资源行
- 由用户通过现有编辑器的采集工具补全
- 在最终配置生成前再由 skill 读回检查

它和运行时脚本资源文件不是一回事。

这个清单文件的规则是：

- 只允许 `resource(pic;alias)` 和 `resource(ocr;alias)`
- 不允许放 `jmp` 资源
- alias 使用语义化命名
- 用 `备注` 说明用户应该采集什么内容

## 骨架复用倾向

优先复用已有配置骨架，而不是从零生成全新结构。

在检查已有项目配置时，重点看：

- 是否反复出现诸如 `check.csv`、`pending.csv`
- 是否反复使用相同 OCR 锚点
- 是否存在相同的恢复循环
- 是否已经形成命名模式

只有在当前流程和现有结构差异已经大到继续复用会制造混乱时，才创建全新结构。
