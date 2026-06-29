# CsvAutoGui 项目速览

## 项目定位

- 这是一个 **Windows 专用** 的 Python 自动化项目，核心思路是：用 `config/<name>/*.csv` 描述流程，由运行时解释执行。
- 项目包含三个主要入口：
  - `main.py`：命令行运行器，执行某个配置目录下的自动化流程。
  - `mainWindow.py`：Tk 管理器，可同时启动/停止多个实例并查看日志。
  - `python -m csv_editor`：PySide6 可视化 CSV 编辑器。

## 目录结构

- `autogui/`：运行时核心。包含 CSV 解析、流程解释器、前后台输入、OCR、脚本运行时、截图/录制模式。
- `csv_editor/`：独立编辑器。负责把 CSV 映射为领域模型、做校验、录制、截图回填、未使用图片扫描等。
- `config/`：配置目录根。每个子目录是一套自动化方案，通常至少有 `main.csv`。
- `ocr_model/`：PaddleOCR 本地缓存目录和说明。
- `record/`：录制模式输出。
- `screenshot/`：截图模式输出。
- `scripts/build_release.py`：本地打包脚本，生成 CPU/GPU 发布包。

## 运行模型

1. `main.py` 解析参数并初始化 `ScaleHelper`、OCR 预加载、输入模式。
2. `autogui.parser.GetCsv()` 读取并缓存 CSV，返回 `index -> operation dict`。
3. `autogui.autoOperator.AutoOperator` 按序号解释执行节点。
4. 普通 `pic/ocr` 节点可直接定位，也可走分支跳转或启动子流程。
5. `script` 节点通过 `autogui.script_runtime.execute_script_node()` 加载配置目录内的 Python 脚本执行。

## CSV 约定

- 列定义统一在 `csv_schema.py`。
- 运行时真正依赖的是中文列名，不是编辑器内部字段名。
- `main.csv` 是默认入口；其他普通 `.csv` 可被当作子流程启动。
- `*_resource.csv` 不是流程文件，只给 `script` 节点提供资源。
- 解析缓存键是 `config_path/file_name`，因此修改 CSV 后 **不会自动生效**，必须手动重载。

## 支持的关键节点

- 基础输入：`click` `mDown` `mUp` `mMove` `mMoveTo` `press` `kDown` `kUp` `write`
- 识别节点：`pic` `ocr`
- 控制流：`jmp`
- 扩展能力：`script`
- 资源声明：`resource`
- 提醒：`notify`

补充约定：

- `pic` / `ocr` 没有分支参数时，会持续重试直到命中，然后将鼠标移动到目标中心。
- `pic` 的彩色匹配不是走默认灰度模板匹配，而是 `imageMatcher.py` 中的 `cv2.TM_SQDIFF_NORMED` 分支。
- `write` 实际实现是 `pyperclip.copy(...)` 后发送 `Ctrl+V`，不是逐字输入。

## `pic` / `ocr` 分支语义

- `exist;file.csv` / `notExist;file.csv`：满足条件时启动子流程，子流程结束后回到当前流程下一行。
- `exist;A;B` / `notExist;A;B`：进入双跳转模式，`A/B` 可为序号或跳转标记。

这个分支语义同时被：

- 运行时 `autogui.autoOperator.AutoOperator._handle_branch_result()`
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

脚本入口固定为 `run(ctx)`，推荐继承 `autogui.script_runtime.ScriptBase`。脚本可用能力由 `ScriptContext` 提供，最常用的是：

- `ctx.find_image(...)`
- `ctx.find_text(...)`
- `ctx.start_subflow(...)`
- `ctx.get_resource(...)`
- `ctx.state`

`ctx.state` 是实例级共享字典，主流程、子流程、脚本之间共用。

## 输入模式

- 前台模式：`autogui.frontGroundInput.FrontGroundInput`
  - 直接操作真实鼠标键盘。
  - 截图使用 `pyautogui.screenshot()`。
- 后台模式：`autogui.backGroundInput.BackGroundInput`
  - 通过窗口标题找句柄，主要依赖 `PostMessage` 和 `PrintWindow`。
  - `--multi_window` 会尝试按当前位置匹配子控件句柄。
  - `--click_move_cursor` 会临时移动真实鼠标到目标点点击后恢复。

注意：项目大量依赖 `pywin32`、`keyboard`、`mouse`、`winsound` 和 Windows 窗口行为，默认不考虑跨平台兼容。

## OCR 与缩放

- OCR 入口在 `autogui.ocr.OCR()`，底层使用 PaddleOCR，启动时异步预加载。
- GPU/CPU 版本通过切换不同 `pyproject*.toml` 管理依赖，不是运行时动态切换。
- 数值 OCR 支持比较语法，例如 `<=;1000`。
- `ScaleHelper` 会同时影响：
  - 坐标参数
  - 区域参数
  - 可选的图片模板缩放

## 编辑器结构

- 启动入口：`csv_editor/app.py`
- 主要窗口：`csv_editor/main_window.py`
- 数据模型：`csv_editor/domain/models.py`
- CSV 编解码：`csv_editor/io/csv_codec.py`
- 校验：`csv_editor/services/validation.py`
- 录制转节点：`csv_editor/services/recording.py`

编辑器不是直接操作运行时字典，而是先转成 `OperationNode / FlowDocument / EditorDocument`，保存时再编码回 CSV。

编辑器当前额外承担这些约定：

- 资源文件中只允许 `resource` 节点。
- 普通流程中不能出现 `resource` 节点。
- `重新加载` 会清空 CSV 缓存、脚本缓存、资源缓存。

## 缓存与热更新

运行时存在三类缓存：

- `autogui.parser.csvDataDict`
- `autogui.script_runtime._script_cache`
- `autogui.resource_loader._resource_cache`

因此以下改动都需要手动重载后才会按新内容执行：

- CSV
- `script` Python 文件
- `*_resource.csv`

## 日志与并发

- `autogui.log` 支持线程级 handler 和线程上下文，`mainWindow.py` 依赖它来区分多实例日志来源。
- `mainWindow.py` 的多实例本质上是同进程多线程，不是多进程。
- 子流程通过共享 `subOperatorList` 栈式执行，实例内部共享同一个输入对象和 `state`。

## 新增或修改功能时的高影响点

- 如果改了 CSV 语义，通常要同时检查：
  - `csv_schema.py`
  - `autogui/parser.py`
  - `autogui/autoOperator.py`
  - `csv_editor/io/csv_codec.py`
  - `csv_editor/services/validation.py`
- 如果改了 `script` / `resource` 规则，要同时检查运行时和编辑器校验是否一致。
- 如果改了图片/OCR定位行为，要同时看前台输入和后台输入两套实现。

## 推荐阅读顺序

1. `README.md`：用户视角说明和 CSV 字段定义。
2. `main.py`：运行入口与参数。
3. `autogui/autoOperator.py`：主解释器。
4. `autogui/script_runtime.py` + `autogui/resource_loader.py`：脚本与资源机制。
5. `csv_editor/main_window.py`：编辑器能力边界。

## 当前项目的简短判断

- 这是一个“**CSV 解释执行器 + 图像/OCR识别 + Windows 输入桥接 + 可视化编辑器**”的组合项目。
- 运行时和编辑器各自维护了一套对 CSV 语义的实现；理解或修改项目时，首先确认两边是否同步。
