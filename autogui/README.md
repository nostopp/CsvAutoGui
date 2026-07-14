# `autogui` 运行时结构

`autogui` 已按职责拆分为领域子包。根目录 `__init__.py` 只负责 Windows 全虚拟桌面截图初始化，不再承载业务实现或重导出子包 API。

## 子包职责

| 子包 | 职责 | 主要模块 |
| --- | --- | --- |
| `infrastructure/` | 无业务状态的基础设施 | `paths.py`、`log.py`、`scaling.py` |
| `input/` | 前台、后台和 watchdog 感知输入 | `base.py`、`foreground.py`、`background.py`、`observed.py`、`image_matcher.py` |
| `vision/` | OCR 与交互式截图工具 | `ocr.py`、`screenshot.py` |
| `flow/` | CSV 原始模型、缓存、加载和强类型编译 | `models.py`、`loader.py` |
| `scripting/` | `script` 节点和 `*_resource.csv` | `runtime.py`、`resources.py` |
| `notifications/` | 本地弹窗和远程通知策略 | `notifier.py`、`runtime.py` |
| `runtime/` | 实例状态、层级配置和缓存协调 | `context.py`、`config.py`、`cache.py` |
| `execution/` | 节点解释、会话、watchdog 和 recovery | `operator.py`、`session.py`、`watchdog.py`、`recovery.py` |

## 依赖方向

- `infrastructure` 不依赖其他运行时领域包。
- `flow` 只依赖共享契约和 `infrastructure`，不依赖执行器。
- `input`、`vision`、`scripting`、`notifications` 提供独立能力，不持有主流程生命周期。
- `runtime` 组合配置、流程、输入、脚本资源和实例缓存。
- `execution` 位于最上层，负责组合其余领域并驱动流程。
- 子包 `__init__.py` 保持轻量；包内代码应直接导入具体模块，避免通过根 `autogui` 反向导入。

新代码应使用规范路径，例如：

```python
from autogui.execution.session import FlowRuntimeSession
from autogui.flow.loader import load_raw_flow
from autogui.runtime.context import RuntimeContext
from autogui.scripting.runtime import ScriptBase
```

旧的平铺模块路径和根包 API 重导出均已删除。配置脚本、框架代码和测试必须直接从上表对应的领域子包导入；错误的旧路径应立即触发 `ModuleNotFoundError`，不得重新添加别名或 wrapper 掩盖迁移遗漏。

流程执行只接受 `CompiledFlow` 和 `RuntimeContext`。旧 `GetCsv()`、`csvDataDict`、operation dict 执行入口和无 Context fallback 均已删除；脚本公开的 `ctx.node` 是专用字典快照，不是执行器内部数据结构。

## OCR 预加载

- `main.py` 每次启动 CLI/Manager 实例时都会调用 `autogui.vision.ocr.startPreload()`。
- `mainWindow.py` 和 `csv_editor/app.py` 会在创建主窗口前调用同一预加载入口。
- `startPreload()` 会立即创建后台线程，导入 PaddleOCR 并初始化引擎；主线程继续启动界面或准备运行实例。
- 第一次真正执行 OCR 时，如果后台初始化尚未结束，只等待剩余初始化时间，不会到那时才开始导入 Paddle。
- 不得把预加载移动到 `OCR()`、Inspector OCR 按钮或其他首次使用路径。

## 结构验收

`tests/runtime/test_package_structure.py` 固定以下规则：

- 每个旧路径都必须不可导入，根包也不得重新导出旧 API。
- `autogui/` 根目录不得重新出现旧平铺模块文件。
- 框架、CSV Editor 和 `config/example` 不得导入旧模块路径。
- 单独导入根包不得隐式加载执行器、脚本运行时或 OCR。

调整目录或模块名时，应先同步结构测试，再运行完整测试集。
