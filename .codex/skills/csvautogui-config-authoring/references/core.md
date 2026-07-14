# 核心规则

## 契约来源

编写语法或运行时结构时，按以下顺序确认事实：

1. 当前源码契约，如 `csv_schema.py`、`operation_contracts.py`、运行时解析器和编辑器校验器；
2. 保持同步的 `config/example/`；
3. 当前 `README.md` 与仓库根目录 `AGENTS.md`。

其他 `config/` 只能提供业务流程、锚点选择和拆分方式的灵感。不要从其他配置复制旧模块导入、旧运行时结构或未经当前契约验证的字段。

## 配置文件事实

- CSV 必须使用 `csv_schema.py` 定义的中文列名。
- `main.csv` 是默认入口。
- 其他普通 `.csv` 可以作为子流程。
- 节点序号必须是唯一整数；运行时保留非连续序号，不要在只读审查中把序号缺口误判为错误。
- `recovery.csv` 是可选的 config 级统一恢复流程，也是普通流程文件。
- `*_resource.csv` 只允许 `resource` 节点，不能作为子流程执行。
- `runtime.json` 是可选的层级运行策略文件，不承载业务流程。
- 脚本、图片、子流程和资源路径都必须解析到当前配置目录内部。

## 分支与跳转

- `exist;file.csv` 和 `notExist;file.csv` 在条件满足时启动子流程，子流程结束后回到当前流程下一行。
- `exist;A;B` 和 `notExist;A;B` 是双跳转；`A/B` 可以是当前流程中的有效序号或跳转标记。
- 没有分支参数的 `pic/ocr` 会持续重试直到命中，然后把鼠标移动到目标中心。
- `jmp` 只能指向当前流程中存在的序号或跳转标记。
- 修改分支语义时必须同时考虑运行时与编辑器，但配置编写任务本身不得发明新语义。

## CSV 与 script 的选择

优先使用 CSV 表达：

- 固定顺序的点击、按键和输入；
- 单次 `pic/ocr` 判断；
- 简单双跳转；
- 边界清晰的静态子流程。

只有以下情况才优先使用 script：

- 需要跨多次观察维护状态；
- 需要计算、循环或动态选择资源；
- 同一判断逻辑会在 CSV 中形成大量重复节点；
- 跳转图已经明显难以验证和维护。

不要只为执行一串固定点击或按键而创建 script。

## script 契约

- 脚本入口固定为顶层 `run(ctx)`。
- 推荐继承 `ScriptBase` 时，只使用当前导入：

  ```python
  from autogui.scripting.runtime import ScriptBase
  ```

- `script` 参数只能是 `some_script.py` 或 `some_script.py;some_resource.csv`。
- 未显式指定资源文件时，运行时尝试加载同名 `some_script_resource.csv`；文件不存在不会报错。
- 显式资源文件必须存在且以 `_resource.csv` 结尾。
- 脚本文件和资源文件都必须位于当前配置目录内。
- `ctx.state` 是主流程、子流程和普通脚本共享的实例级业务状态。
- `ctx.node` 是当前节点的独立字典快照；修改它不会改变已编译流程，也不能用它修改后续执行计划。


脚本应通过传入的 `ctx` 使用 `find_image`、`find_text`、`start_subflow`、`get_resource`、`state` 和输入对象，不直接调用框架内部调度入口。

## 运行时资源

运行时 `*_resource.csv` 只允许：

- `操作=resource`、`操作参数=pic;alias`；
- `操作=resource`、`操作参数=ocr;alias`；
- `操作=resource`、`操作参数=jmp;alias`。

alias 必须唯一且表达业务用途。运行时资源文件只有在被 script 显式引用，或作为已引用 script 的同名默认资源文件时才应保留。

阶段性编写清单也使用 `_resource.csv` 后缀，但不能包含 `jmp`。最终交付前必须把它转换为真实运行时资源，或明确清理。

## runtime.json

`runtime.json` 默认从仓库 `config/runtime.json` 开始，沿当前 config 路径从父到子递归合并：

- 对象字段递归合并；
- 标量、数组和 `null` 由子目录整值覆盖。

允许的主要结构是：

- `watchdog.mode`
- `watchdog.stall_timeout_seconds`
- `watchdog.stall_non_progress_ops`
- `watchdog.recovery_limit`
- `watchdog.recovery_watchdog.stall_timeout_seconds`
- `watchdog.recovery_watchdog.stall_non_progress_ops`
- `on_stall_unresolved.local_notify`
- `on_stall_unresolved.remote_notify`
- `notification.notify_operation.local_notify`
- `notification.notify_operation.remote_notify`
- `notification.remote.enabled`
- `notification.remote.sendkey`
- `notification.remote.sendkey_env`

禁止生成顶层 `recovery_watchdog`。恢复阈值只能放在 `watchdog.recovery_watchdog`；`recovery_limit` 只能放在 `watchdog`。

字段回落顺序：

- 主流程：`watchdog -> 框架默认值`；
- recovery：`watchdog.recovery_watchdog -> watchdog -> 框架默认值`。

`watchdog.mode` 只能是 `off`、`auto`、`on`。`auto` 只会因为当前 config 存在 `recovery.csv`，或 `on_stall_unresolved.remote_notify=true` 而启用；本地通知不影响自动启用。`recovery_limit < 0` 表示无限次恢复。

## watchdog 进展语义

- 点击、按键、输入等真实外部输入属于有效操作。
- `notify`、`mMove`、`mMoveTo` 不刷新 watchdog 进展。
- 观察、判断和跳转不刷新进展。
- `ctx.find_image`、`ctx.find_text`、`ctx.sleep` 只记录观察。
- 通过 `ctx.input` 执行的真实输入会参与有效操作统计。

设计流程时，不能把持续 OCR、移动鼠标或发送通知误当成避免 stall 的进展。

## recovery 状态隔离

- recovery 的职责是把外部系统带回能够从 `main.csv` 重新开始的状态。
- recovery 使用独立的临时状态，不能假定能够读取主流程的业务 `ctx.state`。
- recovery 成功后，原主流程业务状态会被丢弃，并以新的空字典重启整个 config。
- recovery 缺失、超限、失败或再次 stall 时进入 `on_stall_unresolved`，按策略通知后终止当前实例。

## 缓存与重载

以下内容修改后都不会自动热更新，交付时必须提醒用户手动“重新加载”：

- 普通 CSV；
- `recovery.csv`；
- `runtime.json`；
- script Python 文件；
- `*_resource.csv`。
