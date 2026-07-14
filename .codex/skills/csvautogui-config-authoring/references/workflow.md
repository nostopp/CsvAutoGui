# 工作流

## 先确定模式与范围

开始前明确：

- 目标 config 的绝对或仓库相对路径；
- 创建、修改、审查、运行策略、脚本扩展中的哪一种或哪几种模式；
- 用户允许写入的文件范围；
- 是否已有可复用资源和可参考骨架。

可以读取其他 config，但写入只发生在选定目标 config。工作树已有改动属于用户，必须保留并围绕它们工作。

## 阶段 1：确认流程

目标是把自然语言需求整理成可验证的紧凑流程规格。

检查目标项目目录、最接近的业务骨架、当前文件和现有资源。其他 config 只提供业务参考；语法和 API 以 `core.md` 中的契约来源为准。

流程规格至少输出：

- 配置名和目标目录；
- 起始状态、主循环或结束条件；
- 阶段、状态及其转移条件；
- 正常、异常和恢复路径；
- 每个 `pic/ocr` 锚点及其用途；
- CSV、子流程或 script 的选择理由；
- watchdog、recovery 和通知策略；
- 预期创建、修改和保留的文件；
- 会改变实现的未决问题。

用户明确确认规格，或用户提供的规格已经完整且直接要求实施后，才能进入写入阶段。

## 阶段 2：准备资源

只有新增或替换 `pic/ocr` 锚点时才执行。

如有需要，创建目标目录和 `<config_name>_resource.csv`。使用 `csv_schema.py` 的完整中文表头，只预填当前已确认流程真正需要的新资源：

- `操作` 只能是 `resource`，`操作参数` 只能是 `pic;alias` 或 `ocr;alias`；
- 不允许 `操作参数=jmp;alias`；
- alias 使用阶段和用途明确的语义化名称；
- `备注` 描述用户应采集的画面或文字，不写内部实现说明；
- OCR 文字明确时可以预填搜索目标；
- pic 文件尚未采集时保持文件名为空，不捏造素材。

本阶段交付：资源清单路径、资源总数、已具备数量、待采集数量，以及每项对应的流程阶段。

## 阶段 3：校验资源

用户完成采集后运行：

```powershell
uv run --no-sync python .codex/skills/csvautogui-config-authoring/scripts/validate_config.py config/<name> --phase resources --manifest <config_name>_resource.csv
```

检查清单只含允许的 resource 类型、alias 唯一、pic 文件存在、pic/OCR 区域完整合法、OCR 目标存在、所有路径位于目标 config 内。

本阶段交付逐项通过/失败报告。任何资源错误或警告都阻止依赖它的最终流程生成；缺失新锚点时回到阶段 2，不自行猜测。

## 阶段 4：生成或修改配置

按已确认规格和已验证资源生成最小、可读的结构：

- `main.csv`；
- 必要的子流程 CSV；
- 必要时的 `recovery.csv`；
- 必要时的 `runtime.json`；
- 只有满足 script 选择标准时才生成 Python 脚本；
- 只有被脚本实际使用时才保留运行时 `*_resource.csv`。

生成时：

- 固定动作和简单分支优先 CSV；
- 阶段职责清晰时拆成子流程；
- `recovery.csv` 只负责恢复到可从 `main.csv` 重启的外部状态；
- recovery 不读取或依赖主流程业务 state；
- `runtime.json` 只表达运行策略；
- recovery 阈值只写在 `watchdog.recovery_watchdog`；
- 脚本使用 `autogui.scripting.runtime` 和传入的 `ctx`；
- 不复制其他 config 的旧导入或运行时结构。

本阶段交付精确文件列表，分别标明创建、修改、保留和建议清理。

## 阶段 5：校验最终输出

先运行确定性校验：

```powershell
uv run --no-sync python .codex/skills/csvautogui-config-authoring/scripts/validate_config.py config/<name>
```

再按 `validation.md` 做与本次任务相关的语义复核：

- 流程规格是否完整落入节点和分支；
- 资源引用是否与已验证锚点一致；
- watchdog 是否可能把纯观察循环判断为 stall；
- recovery 是否真正回到可重启状态；
- 尚未执行的真实 UI 行为是否明确说明。

最终交付前处理阶段性 `<config_name>_resource.csv`：

- 被 script 正式引用时，说明它已经转为运行时资源；
- 未被 script 使用时，征得用户同意后删除；未获授权时列为阻止最终校验通过的待清理项；
- 仍用于待采集资源时，配置不能标记为最终完成。

本阶段交付校验命令、退出结果、错误和警告数量、未验证项，以及手动重新加载提示。

## 修改模式

修改已有配置时先加载并验证现状，区分既有问题与本次引入的问题。只收集新增或变化的资源，不重建已经有效的资源清单。保持用户现有文件命名和结构，除非它们正是重构目标。

## 审查模式

审查模式保持只读：

1. 确认目标配置与预期业务流程；
2. 运行最终校验；
3. 检查流程语义、资源生命周期和真实 UI 风险；
4. 按严重度报告发现，不创建目录、清单或修复文件。

## 运行策略模式

只调整 `runtime.json`、watchdog 阈值或通知策略时，读取从 `config/` 根到目标 config 的全部层级 `runtime.json`，说明最终合并效果。没有新增识别锚点时跳过阶段 2、3。

只校验运行参数时使用：

```powershell
uv run --no-sync python .codex/skills/csvautogui-config-authoring/scripts/validate_config.py config/<name> --phase runtime
```

修改 `recovery.csv` 或 recovery 脚本不属于纯运行策略调整，必须同时进入修改模式，并验证其流程、资源和状态隔离。

## 脚本扩展模式

先记录使用 script 而非 CSV 的具体理由。检查现有流程和脚本引用，只为脚本真正需要的数据创建运行时资源；不要为固定点击序列包装脚本。

脚本入口、导入、上下文能力、默认资源文件和禁止的旧接口以 `core.md` 为准。

## 项目知识

任务完成后可以提出 `references/projects-local/` 的候选更新，但默认不直接写入。只有用户明确要求维护项目知识时，才记录已经验证且可复用的业务骨架、锚点习惯、恢复分支、命名约定或高价值坑点。

不要把框架 API、一次性状态或未经运行验证的推测写入项目知识。
