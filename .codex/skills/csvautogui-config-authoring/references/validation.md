# 校验与交付

## 确定性校验

最终配置默认运行：

```powershell
uv run --no-sync python .codex/skills/csvautogui-config-authoring/scripts/validate_config.py config/<name>
```

资源采集完成后运行：

```powershell
uv run --no-sync python .codex/skills/csvautogui-config-authoring/scripts/validate_config.py config/<name> --phase resources --manifest <config_name>_resource.csv
```

仅调整或审查层级 `runtime.json` 时可以运行：

```powershell
uv run --no-sync python .codex/skills/csvautogui-config-authoring/scripts/validate_config.py config/<name> --phase runtime
```

脚本复用仓库当前的 `CsvEditorCodec`、`validate_document`、`RuntimeConfigResolver`、`operation_contracts` 和 `csv_schema`，再补充 skill 的严格交付规则。`runtime.json` 的允许字段结构从保持最新的 `config/example/runtime.json` 递归派生，字段值仍交给 `RuntimeConfigResolver` 校验。它是只读工具，不会自动修复或改写配置。

退出码为 0 才表示结构校验通过。最终阶段中，编辑器级 warning 也视为未解决问题；必须修复。无法修复时可以向用户报告并移交，但不能宣称最终校验已经通过。

## CSV 与流程

- 存在 `main.csv`，且所有 CSV 使用当前完整中文表头。
- 节点序号是唯一整数；允许运行时支持的非连续序号，并按原始序号校验数值跳转。
- 普通流程和 `recovery.csv` 中没有 `resource` 节点。
- `*_resource.csv` 中只有 `resource` 节点。
- 原始操作名、跳转标记和图片文件名没有会被编辑器静默去掉的首尾空格。
- 两个 CSV 布尔列只使用空值、`0` 或 `1`，不会在运行时转换整数时失败。
- 分支子流程存在、位于目标 config 内，且不是资源文件。
- `jmp`、双跳转序号和跳转标记在当前流程中真实存在。
- 同一普通流程内跳转标记唯一，同一资源文件内 alias 唯一；两者不是同一个命名空间。
- 普通 pic 和资源 pic 引用的图片存在、是普通文件且路径不越界。
- 数字、区域、置信度、等待和重试字段符合当前操作契约。

## 编写清单与运行时资源

阶段 3 的编写清单：

- 只允许 `pic` 和 `ocr` 资源，不允许 `jmp`；
- pic 和 OCR 都必须填写合法的 `x;y;w;h` 区域；
- pic 必须有真实图片，OCR 必须有目标文字；
- alias 必须唯一并能表达阶段或用途。

最终配置中的 `*_resource.csv` 必须被某个 script 显式引用，或是已引用脚本存在的同名默认资源文件。未引用文件说明阶段性清单尚未处理，或者存在无效运行时资源，不能无说明交付。

## script

- 每个被引用的入口脚本存在、是普通文件、路径不越界且能通过 Python 语法解析。
- 入口脚本提供顶层 `run(ctx)`。
- 使用 `ScriptBase` 时从 `autogui.scripting.runtime` 导入。
- 不使用 `autogui.script_runtime`、`autogui.flow.parser`、`GetCsv` 或 `csvDataDict`。
- 不直接构造 `ScriptContext`，不直接调用 `execute_script_node()`。
- script 文件后缀严格使用小写 `.py`，显式资源文件后缀严格使用小写 `_resource.csv`，与当前运行时大小写规则一致。
- 脚本把 `ctx.node` 当作只读快照，不依赖修改它改变已编译流程。

## runtime.json

- JSON 可解析且根节点为对象或 `null`。
- 只使用当前支持的顶层和子级字段，避免拼写错误被运行时静默忽略。
- `watchdog.mode` 只能是 `off`、`auto`、`on`。
- 超时和非进展操作阈值大于 0。
- `recovery_limit` 能转换为整数，负数表示无限恢复。
- 不存在顶层 `recovery_watchdog`。
- recovery 阈值位于 `watchdog.recovery_watchdog`，其中不放 `mode` 或 `recovery_limit`。
- 通知字段是运行时接受的布尔值，sendkey 字段结构正确。
- 同时考虑父级与当前 config 的层级合并结果。

## 业务语义复核

机械校验不能证明真实 UI 自动化正确，还要人工确认：

- 每个状态都有进入条件和离开路径；
- `exist/notExist` 方向与用户确认的业务含义一致；
- 子流程结束后回到当前流程下一行是否符合预期；
- 无分支 `pic/ocr` 的无限重试是否有意为之；
- watchdog 阈值是否适合包含大量观察节点的流程；
- recovery 能否在不读取主流程 state 的情况下恢复外部状态；
- recovery 脚本是否只使用自己的临时 state，而没有假定能读到主流程业务 `ctx.state`；
- stall 终态和普通 notify 的通知策略没有混淆。

不能实际操作目标应用时，要把这些项目列为“未进行真实 UI 验证”，不能把静态校验描述成端到端运行成功。

## 写入范围复核

- 只改动用户指定的目标 config。
- 没有修改参考骨架或其他 config。
- 没有覆盖、移动或删除用户素材。
- 没有生成越出目标 config 的引用。
- `projects-local` 只在获得明确授权后更新。

## 最终报告

最终回复至少说明：

- 创建、修改、保留和建议清理的文件；
- 校验命令、退出码、错误与警告数量；
- 未执行或无法执行的真实 UI 验证；
- CSV、`recovery.csv`、`runtime.json`、script 或 `*_resource.csv` 发生变化时，需要在运行前手动“重新加载”。
