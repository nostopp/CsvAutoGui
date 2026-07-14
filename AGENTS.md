# CsvAutoGui 项目速览

## 项目定位

- 这是一个 **Windows 专用** 的 Python 自动化项目，核心思路是：用 `config/<name>/*.csv` 描述流程，由运行时解释执行。
- 项目包含三个主要入口：
  - `main.py`：命令行运行器，执行某个配置目录下的自动化流程。
  - `mainWindow.py`：Tk 管理器，可同时启动/停止多个实例并查看日志。
  - `python -m csv_editor`：PySide6 可视化 CSV 编辑器。

## 目录结构

- `autogui/`：运行时核心，按 `infrastructure/`、`input/`、`vision/`、`flow/`、`scripting/`、`notifications/`、`runtime/`、`execution/` 分包；详细职责和依赖规则见 `autogui/README.md`。
- `csv_editor/`：独立编辑器。负责把 CSV 映射为领域模型、做校验、录制、截图回填、未使用图片扫描等。
- `config/`：配置目录根。每个子目录是一套自动化方案，通常至少有 `main.csv`。
- `ocr_model/`：PaddleOCR 本地缓存目录和说明。
- `screenshot/`：截图模式输出。
- `scripts/build_release.py`：本地打包脚本，生成 CPU/GPU 发布包。

旧的平铺模块路径和 `autogui` 根包 API 重导出已全部删除。仓库实现与 `config/example` 必须使用 `autogui/README.md` 中的规范路径；不得重新添加旧路径别名、wrapper，或在子包实现中通过根 `autogui` 反向导入。

## 运行模型

1. `main.py` 解析参数并初始化 `ScaleHelper`、OCR 预加载、输入模式。
2. `autogui.flow.loader.RawFlowCache` 进程级缓存未缩放的不可变 CSV 数据；每个实例的 `RuntimeContext` 再按自己的 `ScaleHelper` 编译为 `CompiledFlow`。执行器只接受强类型 `CompiledFlow`，不再提供旧字典 parser facade。
3. `main.py` 会先解析层级 `runtime.json`，再按 `watchdog.mode` 判断是否创建 watchdog 运行时。
4. `autogui.execution.session.FlowRuntimeSession` 统一管理普通、watchdog 和 recovery 的 entry flow、主流程与子流程栈；`autogui.execution.operator.AutoOperator` 按序号解释执行具体节点。
5. 普通 `pic/ocr` 节点可直接定位，也可走分支跳转或启动子流程。
6. `script` 节点通过 `autogui.scripting.runtime.execute_script_node()` 加载配置目录内的 Python 脚本执行。
7. 启用了 watchdog 且当前 config 存在 `recovery.csv` 时，主流程在判定卡死后会执行同目录下的 `recovery.csv`；恢复成功后清空共享业务 `state` 并从 `main.csv` 重启整个 config。
8. 每次进入 stall 处理链时，运行时都会额外抓取一张完整虚拟桌面的全屏截图，输出到 `screenshot/stall_{config_name}_{flow}_{index}_{timestamp}.png`，与前后台模式和目标窗口配置无关。

## CSV 约定

- 列定义统一在 `csv_schema.py`。
- 操作名称、分类、参数类型、flow 允许范围、字段支持与稳定默认值统一在根模块 `operation_contracts.py`；该模块只能依赖标准库，不能导入 runtime、Qt、Tk、PaddleOCR 或 Windows API。
- 运行时真正依赖的是中文列名，不是编辑器内部字段名。
- `main.csv` 是默认入口；其他普通 `.csv` 可被当作子流程启动。
- `recovery.csv` 是可选的 config 级统一恢复流程；是否启用 watchdog 由 `runtime.json.watchdog.mode` 决定。
- `*_resource.csv` 不是流程文件，只给 `script` 节点提供资源。
- `runtime.json` 是可选的层级运行参数文件，用来配置 watchdog / recovery 阈值、stall 终态通知以及 `notify` 节点通知策略。
- `runtime.json` 默认从 `config/` 根目录开始，沿当前 config 路径逐级合并；它的加载与 `recovery.csv` 是否存在无关。
- RawFlow 缓存键是规范化后的 `config_path/file_name`，因此修改 CSV 后 **不会自动生效**，必须手动重载；CompiledFlow、图片、资源和业务 state 均为实例所有。

## 支持的关键节点

- 基础输入：`click` `mDown` `mUp` `mMove` `mMoveTo` `press` `kDown` `kUp` `write`
- 识别节点：`pic` `ocr`
- 控制流：`jmp`
- 扩展能力：`script`
- 资源声明：`resource`
- 提醒：`notify`

补充约定：

- `pic` / `ocr` 没有分支参数时，会持续重试直到命中，然后将鼠标移动到目标中心。
- `pic` 的彩色匹配不是走默认灰度模板匹配，而是 `autogui/input/image_matcher.py` 中的 `cv2.TM_SQDIFF_NORMED` 分支。
- `write` 实际实现是 `pyperclip.copy(...)` 后发送 `Ctrl+V`，不是逐字输入。
- 启用了 watchdog 的 config 会按“无进展窗口”判定卡死：自上一次有效操作以来，如果持续只有观察/跳转类动作，并同时超过时间阈值与非有效操作次数阈值，就会进入 stall 处理链。
- 若 stall 后没有 `recovery.csv`、recovery 超限、recovery 失败或 recovery 再次 stall，就会进入 `on_stall_unresolved` 终态：按配置通知后终止当前实例。
- `notify`、`mMove`、`mMoveTo` 不算有效操作；脚本中的 `ctx.find_image`、`ctx.find_text`、`ctx.sleep` 也只算观察，不会刷新 watchdog。

## `pic` / `ocr` 分支语义

- `exist;file.csv` / `notExist;file.csv`：满足条件时启动子流程，子流程结束后回到当前流程下一行。
- `exist;A;B` / `notExist;A;B`：进入双跳转模式，`A/B` 可为序号或跳转标记。

这个分支语义同时被：

- 运行时 `autogui.execution.operator.AutoOperator._handle_branch_result()`
- 编辑器 `csv_editor.io.csv_codec.CsvEditorCodec`

共同实现，修改时需要保持一致。

## `script` / `resource` 机制

- `script` 参数格式：
  - `some_script.py`
  - `some_script.py;some_resource.csv`
- 未显式指定资源文件时，默认尝试同名 `some_script_resource.csv`；不存在也不会报错。
- 显式指定资源文件时，文件必须存在且文件名以 `_resource.csv` 结尾。
- 脚本文件和资源文件都被限制在当前配置目录内，禁止越界路径。

`*_resource.csv` 只允许 `resource` 节点：

- `resource;pic;alias` 的真实 CSV 表现是 `操作=resource`，`操作参数=pic;alias`
- `resource;ocr;alias`
- `resource;jmp;alias`

脚本入口固定为 `run(ctx)`，推荐继承 `autogui.scripting.runtime.ScriptBase`。脚本可用能力由 `ScriptContext` 提供，最常用的是：

- `ctx.find_image(...)`
- `ctx.find_text(...)`
- `ctx.start_subflow(...)`
- `ctx.get_resource(...)`
- `ctx.state`

`ctx.state` 是实例级共享字典，主流程、子流程、脚本之间共用。
如果 recovery 成功并整 config 重启，这个共享字典会被清空后重建。

## `runtime.json` / watchdog 约定

- `runtime.json` 搜索范围：默认从仓库 `config/runtime.json` 一直到当前 config 目录下的 `runtime.json`
- 字段：
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
- 层级合并：
  - 父目录先加载，子目录后覆盖
  - 对象字段递归合并
  - 标量、数组、`null` 按子目录整值覆盖
- 字段回落：
  - 主流程：`watchdog -> 框架默认值`
  - recovery 流程：`watchdog.recovery_watchdog -> watchdog -> 框架默认值`
- `watchdog.mode=auto` 只会因为当前 config 存在 `recovery.csv`，或 `on_stall_unresolved.remote_notify=true` 而自动启用 watchdog；本地通知不会影响这个判定。
- `runtime.json` 是否存在不会影响 `recovery.csv` 是否可用；但 watchdog 是否启动不再只由 `recovery.csv` 决定。
- `recovery_limit < 0` 表示无限次恢复。

## 输入模式

- 前台模式：`autogui.input.foreground.FrontGroundInput`
  - 直接操作真实鼠标键盘。
  - 截图使用 `pyautogui.screenshot()`。
- 后台模式：`autogui.input.background.BackGroundInput`
  - 通过窗口标题找句柄，主要依赖 `PostMessage` 和 `PrintWindow`。
  - `--multi_window` 会尝试按当前位置匹配子控件句柄。
  - `--click_move_cursor` 会临时移动真实鼠标到目标点点击后恢复。

注意：项目大量依赖 `pywin32`、`keyboard`、`mouse`、`winsound` 和 Windows 窗口行为，默认不考虑跨平台兼容。

## OCR 与缩放

- OCR 入口在 `autogui.vision.ocr.OCR()`，底层使用 PaddleOCR。CLI 实例、Manager 和 CSV Editor 必须在启动阶段调用 `startPreload()` 异步导入并初始化 Paddle；不得改成首次调用 `OCR()` 时才开始加载。
- GPU/CPU 版本通过切换不同 `pyproject*.toml` 管理依赖，不是运行时动态切换。
- 数值 OCR 支持比较语法，例如 `<=;1000`。
- `ScaleHelper` 会同时影响：
  - 坐标参数
  - 区域参数
  - 可选的图片模板缩放

## 编辑器结构

- 启动入口：`csv_editor/app.py`
- 主要窗口：`csv_editor/main_window.py`
- 文档控制器：`csv_editor/controllers/document_controller.py`
- 变更描述与影响级别：`csv_editor/controllers/change_set.py`
- 数据模型：`csv_editor/domain/models.py`
- 节点差量：`csv_editor/domain/node_patch.py`
- CSV 编解码：`csv_editor/io/csv_codec.py`
- 校验：`csv_editor/services/validation.py`
- 录制转节点：`csv_editor/services/recording.py`
- 节点属性面板：`csv_editor/widgets/node_inspector.py`
- 简单字段绑定：`csv_editor/widgets/field_bindings.py`

编辑器不是直接操作运行时字典，而是先转成 `OperationNode / FlowDocument / EditorDocument`，保存时再编码回 CSV。

编辑器当前额外承担这些约定：

- 资源文件中只允许 `resource` 节点。
- 普通流程中不能出现 `resource` 节点。
- `重新加载` 会清空 CSV 缓存、脚本缓存、资源缓存。
- `NodeInspector` 只发送包含实际差异字段的不可变 `NodePatch`；不要恢复整份 `OperationNode` 写回信号。
- 简单字段使用 `FieldBinding` 声明；branch、resource、script、jump、图片预览和采集按钮继续使用专用 builder。
- 活动 document、current flow/node、codec 调用、validation 和节点结构修改由 `EditorDocumentController` 统一持有；MainWindow 只能通过只读代理访问活动模型。
- Undo command 只依赖 Controller，并通过 callback 返回 `EditorChangeSet`；不得重新引用 window 或调用 `_refresh_*` 私有方法。
- 连续节点编辑仍按同 flow/node 合并 undo，合并时必须同时合并最终 snapshot 和 `changed_fields`。
- PIC/OCR/取点回填在 MainWindow 中构造多字段 `NodePatch`，不得临时修改 live node 再回滚。
- Controller 按 flow/node 分桶保存 issues：`DISPLAY_ONLY` 不校验，`NODE_VALIDATION` 只替换目标节点，`REFERENCE_GRAPH/FLOW_STRUCTURE` 只重校验目标 flow，打开/重新加载/保存才全量 `validate_document()`。
- 普通字段编辑只能调用 `update_node_rows()`，不得调用 `refresh_flow_table()`；row map 无效时允许且必须 fallback 全量刷新。
- 引用变化会原位更新当前 flow 全部行，以同步 target role、tooltip、颜色和 warning；不要为此恢复整表 setRowCount 重建。
- Inspector 普通字段通过 `sync_node()` 原位回填；只有 operation、branch mode 或 resource kind 改变时重建，jump/branch 候选项由 `set_reference_data()` 原位更新。
- CSV preview 使用按 flow 的 dirty/cache，只有用户打开预览时编码；保存不得读取预览缓存。
- 录制模式只存在于 CSV Editor；CLI `--record` 和旧 `RecordMode` 已删除。录制结果是剪贴板草稿节点，必须粘贴到目标 flow 后再保存，不会直接改 CSV。
- 录制支持屏幕绝对坐标和目标窗口内坐标，可选子窗口匹配；悬浮条提供 OCR/PIC 出现、消失、定位标记以及暂停/停止。

## 缓存与热更新

运行时缓存按所有权分层：

- 进程级 `autogui.flow.loader.RawFlowCache`
- `autogui.scripting.runtime._script_cache`
- 实例级 `RuntimeContext.compiled_flows`
- 实例级 `RuntimeContext.image_cache`
- 实例级 `RuntimeContext.resource_cache`

Manager 和 CSV Editor 的重新加载统一调用 `autogui.runtime.cache.clear_runtime_caches()`；界面层不应直接操作缓存变量。存活实例的 compiled/image/resource 缓存随实例生命周期结束，不会被全局入口跨线程强制修改。

因此以下改动都需要手动重载后才会按新内容执行：

- CSV
- `recovery.csv`
- `runtime.json`
- `script` Python 文件
- `*_resource.csv`

## 日志与并发

- `autogui.infrastructure.log` 支持线程级 handler 和线程上下文，`mainWindow.py` 依赖它来区分多实例日志来源。
- `mainWindow.py` 的多实例本质上是同进程多线程，不是多进程。
- Manager 的实例线程和全局热键回调禁止调用 Tk API；它们只写入 `queue.SimpleQueue` 或设置线程事件，主线程通过单一 50ms drain job 批量处理日志与状态。
- 每个实例使用 `manager_logs.InstanceLogBuffer` 保留最近 5000 条日志；buffer 淘汰文本时，当前 Text 必须在同一批次按 Tcl 字符数同步头删。
- 日志搜索以 `tag_ranges()` 为实时来源，查询变更 debounce 200ms，新日志仅扫描新增区间；不要恢复长期缓存的字符串 Text index，也不要在每条日志后全文搜索。
- Manager 关闭时必须取消 drain/search after job 并拒绝迟到日志；窗口生命周期内实例 ID 不复用。
- `autogui.notifications.notifier` 的弹窗线程使用自己创建的 Tk root，不得借用 Manager 默认 root 调用跨线程 `after()`。
- 普通、watchdog 和 recovery 都通过 `autogui.execution.session.FlowRuntimeSession` 管理共享 `subOperatorList`，实例内部共享同一个 `RuntimeContext`、输入对象和 `state`。

## 新增或修改功能时的高影响点

- 如果改了 CSV 语义，通常要同时检查：
  - `csv_schema.py`
  - `operation_contracts.py`
  - `autogui/flow/loader.py`
  - `autogui/flow/models.py`
  - `autogui/execution/operator.py`
  - `csv_editor/io/csv_codec.py`
  - `csv_editor/services/validation.py`
- 运行时和编辑器统一直接从 `operation_contracts` 导入 `OperationType`；不得在领域子包重新导出或建立第二份枚举。
- 新增操作时必须先增加唯一 `OperationContract`，再让 parser、validation、summary、recording 和 Inspector 消费；不要把 runtime handler、Qt builder、颜色或 watchdog 分类塞进 contract。
- 修改 Inspector 字段时同步检查 `FieldBinding`、`NodePatch` 应用规则和 `OperationContract.supported_fields`；单字段编辑必须只产生该字段 patch。
- 新增编辑器领域修改时必须在 Controller 中返回 `EditorChangeSet`，并在集中映射中定义 `ChangeImpact`；不要把 impact 判断散落到 MainWindow。
- 修改增量刷新时必须保留 ordinary patch 不调用 `refresh_flow_table()`/`validate_document()` 的 500 节点测试，并覆盖 undo/redo 后 Controller、表格 selection 与 Inspector 同步。
- 如果改了 `script` / `resource` 规则，要同时检查运行时和编辑器校验是否一致。
- 如果改了图片/OCR定位行为，要同时看前台输入和后台输入两套实现。
- 如果改了 watchdog / recovery 行为，重点检查：
  - `main.py`
  - `autogui/execution/session.py`
  - `autogui/execution/recovery.py`
  - `autogui/execution/watchdog.py`
  - `autogui/input/observed.py`
  - `autogui/scripting/runtime.py`
  - `README.md` / `AGENTS.md`

## 推荐阅读顺序

1. `README.md`：用户视角说明和 CSV 字段定义。
2. `main.py`：运行入口与参数。
3. `autogui/README.md`：运行时分包、依赖方向和导入规则。
4. `autogui/execution/operator.py`：主解释器。
5. `autogui/scripting/runtime.py` + `autogui/scripting/resources.py`：脚本与资源机制。
6. `csv_editor/main_window.py`：编辑器能力边界。

## 当前项目的简短判断

- 这是一个“**CSV 解释执行器 + 图像/OCR识别 + Windows 输入桥接 + 可视化编辑器**”的组合项目。
- 运行时和编辑器各自维护了一套对 CSV 语义的实现；理解或修改项目时，首先确认两边是否同步。
