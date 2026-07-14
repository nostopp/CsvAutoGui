# CsvAutoGui 自动化工具

本项目通过配置 CSV 文件来进行自动化操作。

---

## 使用说明

本项目使用 [uv](https://docs.astral.sh/uv/) 管理依赖，需先安装 uv。

1. 在 `config` 下新建文件夹并命名。
2. 在其中创建主配置 `main.csv`。
3. 参考 `template` 及 `example` 完成配置（示例图片名格式均为自带截图模式截图，仅保留一个示意）。
4. 运行命令：
   命令行方式运行
   ```powershell
   uv run main.py -c config/文件夹名称
   ```
   图像化运行
   ```powershell
   uv run mainWindow.py
   ```
   CSV 可视化编辑器
   ```powershell
   uv run python -m csv_editor
   ```
5. 修改普通 CSV、`recovery.csv`、`runtime.json`、`script` 脚本或 `*_resource.csv` 后，需要手动执行界面里的“重新加载”；CLI 方式则需结束并重新启动实例。

### 可选的全局恢复机制

- 是否启用 watchdog 由 `runtime.json.watchdog.mode` 决定：
  - `off`：强制关闭 watchdog
  - `auto`：当配置目录存在 `recovery.csv`，或 `on_stall_unresolved.remote_notify=true` 时启用 watchdog
  - `on`：强制启用 watchdog
- 默认值是 `auto`，因此旧配置仍保持兼容语义：只要没有 `recovery.csv` 且没有显式要求 unresolved 远程通知，就不会自动监控卡死。
- stall 语义为“自上次有效操作以来持续无进展”，但只有当自动闭环失败后，才会进入 `on_stall_unresolved` 终态。
- 终态语义为：
  - 主流程 stall 且没有 `recovery.csv`
  - 主流程 stall，但 `recovery_limit` 已达上限
  - `recovery.csv` 抛异常或自己再次 stall
  - 以上情况都会先抓取一次完整虚拟桌面的全屏截图，保存到 `screenshot/stall_{config_name}_{flow}_{index}_{timestamp}.png`
  - 然后按 `on_stall_unresolved` 触发本地通知和/或远程通知，最后终止当前实例
- recovery 成功语义保持不变：
  - 主流程长时间没有产生“有效操作”时，运行时执行 `recovery.csv`
  - `recovery.csv` 正常执行到结尾，就视为恢复成功
  - 恢复成功后会清空本轮运行的共享 `state`，并从 `main.csv` 第一步重新开始

### `runtime.json`

- `runtime.json` 是可选的运行时配置文件，默认从仓库 `config/` 根目录开始，沿着 `config/.../当前配置目录` 逐级向下合并。
- 子目录只需要覆盖自己关心的字段；未覆盖字段会继续继承父目录，再回落到框架默认值。
- 当前支持的字段：

```json
{
  "watchdog": {
    "mode": "auto",
    "stall_timeout_seconds": 60,
    "stall_non_progress_ops": 60,
    "recovery_limit": 3,
    "recovery_watchdog": {
      "stall_timeout_seconds": 30,
      "stall_non_progress_ops": 20
    }
  },
  "on_stall_unresolved": {
    "local_notify": true,
    "remote_notify": false
  },
  "notification": {
    "notify_operation": {
      "local_notify": true,
      "remote_notify": false
    },
    "remote": {
      "enabled": true,
      "sendkey_env": "CSV_AUTOGUI_SERVERCHAN_SENDKEY"
    }
  }
}
```

- 字段回落规则：
  - 主流程：`watchdog.{field} -> 框架默认值`
  - recovery 流程：`watchdog.recovery_watchdog.{field} -> watchdog.{field} -> 框架默认值`
- 层级合并规则：
  - 搜索范围：从 `config/runtime.json` 一直到当前 config 目录下的 `runtime.json`
  - 合并顺序：父目录先加载，子目录后覆盖
  - 对象字段：递归合并
  - 标量、数组、`null`：子目录整值覆盖父目录
- `watchdog.mode` 只支持 `off`、`auto`、`on`。
- `on_stall_unresolved` 只在“自动恢复链已经无法闭环”时触发，不会在首次检测到 stall 时触发。
- `watchdog.mode=auto` 不会因为本地通知可用而自动启用 watchdog；只有 `recovery.csv` 或 `on_stall_unresolved.remote_notify=true` 才会触发自动启用。
- `notification.notify_operation` 控制普通 `notify` 节点的默认通知通道。
- `notification.remote` 当前只支持 [Server酱³](https://sc3.ft07.com/)：
  - `enabled`：是否允许远程发送
  - `sendkey`：直接写死 sendkey
  - `sendkey_env`：从环境变量读取 sendkey；仅当 `sendkey` 未配置时使用
- `recovery_limit` 只属于主流程 `watchdog`。
- `recovery_limit < 0` 表示 recovery 次数无限制。

### 什么算“卡死”

- 只有同时满足下面两项，watchdog 才会判定当前流程 stall：
  - 距离上一次有效操作超过 `stall_timeout_seconds`
  - 自上一次有效操作以来，累计的非有效操作次数达到 `stall_non_progress_ops`
- stall 后不一定立刻通知；只有 recovery 不存在、recovery 超限、recovery 失败或 recovery 再次 stall 时，才会触发 `on_stall_unresolved`。
- 有效操作：
  - `click` `mDown` `mUp` `press` `kDown` `kUp` `write`
  - `script` 中通过 `ctx.input.click/press/keyDown/keyUp/hotkey/...` 发出的真实输入
- 非有效操作：
  - `mMove` `mMoveTo` `pic` `ocr` `jmp` `notify`
  - `script` 中的 `ctx.find_image(...)`、`ctx.find_text(...)`、`ctx.sleep(...)`

### 运行参数

| 参数 | 说明 | 默认值 |
| :-: | :-: | :-: |
| -c / --config | 指定配置文件夹路径 | config/test |
| -l / --loop | 自动化是否循环 | False |
| --log | 是否打印日志 | False |
| -s / --screenshots | 运行在截图模式 | False |
| --scale | 运行分辨率与配置分辨率的比值 | 1 |
| --scale_image | 缩放时是否缩放用到的截图 | False |
| --offset | 运行时对涉及到的绝对坐标进行偏移 | 0;0 |
| -t / --title | 目标窗口名称,指定后程序运行在后台窗口模式 | None |
| -m / --multi_window | 后台窗口多窗口控件模式 | False |
| --click_move_cursor | 后台 `click` 时临时将真实鼠标移动到目标点，点击后快速恢复原位置 | False |
| --process | 获取所有可见窗口名称 | False |

- **终止程序**：按 `Ctrl+Shift+X`

---

## 截图模式

- 按下 `Shift+X`：打印当前坐标，第二次按下将计算与第一次的坐标差值，并将两次坐标间的范围截图保存到 `screenshot` 目录下。
- 按下 `Shift+C`：打印当前坐标，第二次按下将计算与第一次的坐标差值，便于配置填写。
- 按下 `Shift+F`：进行全屏幕截图。

---

## CSV Editor 录制模式

- 录制入口只在 CSV Editor 的“工具 -> 录制模式…”中。
- 先打开目标配置和 flow，再选择坐标模式：
  - “屏幕绝对坐标（FrontInput）”直接记录屏幕坐标。
  - “窗口内坐标（BackInput）”需要选择目标窗口；可选“开启子窗口匹配”，把坐标转换为命中子窗口内的位置。
- 点击“开始录制”后编辑器会最小化并显示悬浮录制条。录制条可暂停/继续、停止，也可添加 OCR/PIC 的“等待出现”“等待消失”“定位目标”标记；`Shift+X` 是备用停止热键。
- PIC 标记会把框选图片保存到当前配置目录；OCR 标记会使用本地 OCR 预览生成候选文本。定位标记后的鼠标动作会尽量转成目标内点击或相对偏移，减少对绝对坐标的依赖。
- 录制结束只生成草稿节点，不会直接写 CSV。请先在审查表检查语义，再“复制选中”或“复制全部”，回到目标 flow 粘贴并保存；离散多选也可以复制。

---

## CSV 各列说明

| 列 | 说明 | 示例（/分开代表不同示例） |
| :-: | :-: | :-: |
| 序号 | 操作会按序号顺序执行，需保证序号从 1 递增 | 1 |
| 操作 | 本次执行的操作，具体内容见下表 | pic |
| 操作参数 | 本次操作的参数，具体内容见下表 | test.png |
| 完成后等待时间 | 操作完成后的等待时间，分号可加入随机等待时间 | 2 / 2;0.5 |
| 图片/ocr名称 | `pic` 操作时图片名称（需带后缀，放在配置文件同目录）；`ocr` 操作时要识别的目标文字。`resource(pic;alias)` / `resource(ocr;alias)` 也复用这一列。若包含数字内容，支持比较大小（<; <=; >; >=; ==; !=;） | test.png / 需识别文字,数字比对<=;1000 |
| 图片/ocr坐标范围 | `pic` 或 `ocr` 操作时识别的屏幕坐标范围，格式为 `起始点x;起始点y;宽;高`，可用截图模式快速定位；资源文件中的 `resource(pic;alias)` / `resource(ocr;alias)` 也复用这一列 | 0;0;1920;1080 |
| 图片/ocr置信度 | `pic` 或 `ocr` 操作时的识别置信度（0-1）；资源文件中的 `resource(pic;alias)` / `resource(ocr;alias)` 也复用这一列 | 0.8 |
| 未找到图片/ocr重试时间 | 未找到目标时且未配置 notExist 参数时的重试时间，支持分号加入随机延迟 | 1 / 1;0.5 |
| 图片/ocr定位移动随机 | 搜索到目标且未使用 exist 等参数时，移动到图片范围中的随机位置 | 1 |
| 移动操作用时 | `mMove` `mMoveTo` `pic` `ocr` 等各种涉及到鼠标移动操作时可控制移动到目标点的用时 | 1 |
| 跳转标记 | `pic` `ocr` `jmp` 等涉及到跳转的操作参数时可用的跳转标记；`resource(jmp;alias)` 使用这一列保存脚本可映射到的真实跳转目标（标记或序号） | 标记名 |
| 图片不使用灰度匹配 | `pic` 匹配时,填1不使用灰度匹配 | 留空 / 1 |
| 备注 | 对该行的备注,仅供编辑csv时查看 | 点击图标 |

---

## 操作类型说明

| 操作名称 | 操作参数 | 说明 |
| :-: | :-: | :-: |
| click | left / middle / right | 鼠标点击 |
| mDown | left / middle / right | 鼠标按下 |
| mUp | left / middle / right | 鼠标松开 |
| mMove | xOffset;yOffset | 鼠标相对坐标移动（参数必须） |
| mMoveTo | xOffset;yOffset | 鼠标绝对坐标移动（参数必须） |
| press | key | 键盘按键（参数必须） |
| kDown | key | 键盘按键按下（参数必须） |
| kUp | key | 键盘按键松开（参数必须） |
| write | text | 键盘输入（参数必须） |
| pic | exist;fileName.csv / notExist;fileName.csv / exist;index;index / notExist;index;index | 识图；双跳转目标为负整数时立即结束当前流程 |
| ocr | exist;fileName.csv / notExist;fileName.csv / exist;index;index / notExist;index;index | OCR 识别；双跳转目标为负整数时立即结束当前流程 |
| script | script.py / script.py;name_resource.csv | 运行配置目录中的 Python 脚本，入口固定为 `run(ctx)` |
| resource | pic;alias / ocr;alias / jmp;alias | 仅用于 `*_resource.csv`，声明脚本可读取的图片、OCR 或跳转资源 |
| notify | text | 通知。默认仍会本地弹窗；是否追加远程通知由 `notification.notify_operation` 控制 |
| jmp | index / 标记 / 负整数 | 跳转；负整数立即结束当前流程 |

---

## Script / Resource 用法

- `script` 节点只允许出现在普通流程 CSV 中，例如 `main.csv`。
- `script` 的 `操作参数` 支持两种格式：
  - `fishing.py`
  - `fishing.py;fishing_resource.csv`
- 当 `script` 没有显式指定资源文件时，会默认查找同目录下的 `fishing_resource.csv`。默认资源文件不存在时不会报错；显式写出的资源文件不存在时，编辑器校验会直接报错。
- 资源文件命名约定为 `*_resource.csv`。这类文件不会被当作普通子流程执行，只用于给 `script` 提供资源。
- `*_resource.csv` 中只允许使用 `resource` 节点：
  - `resource` + `pic;fish`：通过 `图片/ocr名称`、`图片/ocr坐标范围`、`图片/ocr置信度` 声明一个图片资源
  - `resource` + `ocr;meter_text`：通过同样的列声明一个 OCR 资源
  - `resource` + `jmp;finish`：通过 `跳转标记` 列声明脚本内部别名到真实跳转目标的映射，真实目标可以是标记名或序号
- 编辑器中打开 `*_resource.csv` 时，只能新增 `resource` 节点；`resource(pic;alias)` 和 `resource(ocr;alias)` 仍然可以继续使用截图回填和 OCR 区域采集能力。
- 当前版本不会自动检测配置变更。修改 `.py`、普通 `*.csv`、`recovery.csv`、`runtime.json` 或 `*_resource.csv` 后，都需要手动点击“重新加载”；CLI 实例需重新启动。
- 这次手动重载的含义是“重载配置”：会统一刷新 CSV 解析缓存、脚本缓存和资源文件缓存。
- CSV 的进程级缓存只保存未缩放、不可变的 RawFlow；缩放后的 CompiledFlow、图片和资源缓存都由每个运行实例自己的 `RuntimeContext` 持有，不会在多实例之间共享坐标、状态或图片对象。
- 当配置启用了 `recovery.csv` 时，脚本里的 `ctx.input` 会自动计入 watchdog 的“有效操作”；`ctx.find_image`、`ctx.find_text`、`ctx.sleep` 会计入“非有效操作”。

操作名称、类别、参数类型、flow 允许范围、字段支持和 PIC/OCR 默认置信度统一定义在根模块 `operation_contracts.py`。运行时 flow compiler 与执行默认值、编辑器 codec/validation/summary/recording/Inspector 都消费同一份 contract；使用方统一从 `operation_contracts` 导入 `OperationType`，编辑器领域层不再重导出该枚举。

### Script 编写建议

- 虽然脚本入口固定是 `run(ctx)`，但实际编写时推荐继承 `ScriptBase`，把控制流返回交给基类 helper 处理，不要直接手写三元组。
- 推荐写法：

```python
from autogui.scripting.runtime import ScriptBase


class ExampleScript(ScriptBase):
    def run(self):
        self.ctx.log.info("脚本开始执行")
        match = self.ctx.find_image(resource="sample_pic")
        if match is None:
            self.ctx.sleep(0.2)
            return self.next_step()
        return self.jump_resource("finish")


def run(ctx):
    return ExampleScript(ctx).run()
```

### `ScriptBase` API

- `self.ctx`
  - 当前脚本上下文对象，几乎所有运行时能力都从这里取。
- `self.jump(target)`
  - 跳到当前调用脚本的 CSV 中某个真实目标。`target` 可以是跳转标记或序号；负整数会立即结束当前流程。
- `self.jump_resource(name)`
  - 读取 `resource(jmp;name)` 对应的真实目标并跳转。适合把脚本逻辑和真实跳转标记解耦。
- `self.next_step()`
  - 正常返回到解释器，继续执行脚本节点的下一行。
- `self.start_subflow(file_name)`
  - 启动一个普通子流程 CSV，然后继续执行下一行。不能传 `*_resource.csv`。

### `ctx` 属性

- `ctx.config_dir`
  - 当前配置目录路径字符串。
- `ctx.node`
  - 当前 `script` 节点对应的运行时字典，可读取当前节点索引、原始参数等信息。
- `ctx.input`
  - 当前实例实际使用的输入对象。前台模式和后台模式都会从这里透传。
  - 常用低级方法包括：`click`、`moveTo`、`moveRel`、`mouseDown`、`mouseUp`、`press`、`keyDown`、`keyUp`、`hotkey`。
- `ctx.scale_helper`
  - 当前实例的缩放辅助对象，通常只有脚本确实要处理缩放细节时才需要直接使用。
- `ctx.log`
  - 日志模块，常用方法：`info(msg)`、`debug(msg)`、`warning(msg)`、`error(msg)`。
- `ctx.state`
  - 当前实例级共享字典。主流程、子流程、脚本之间共享，用于保存运行中状态。
- `ctx.resources`
  - 当前脚本已加载的资源映射，键是资源变量名，值是 `ResourceSpec`。

### `ctx` 方法

- `ctx.resolve_path(path)`
  - 将相对配置目录路径解析为绝对路径；超出配置目录会直接报错。
- `ctx.get_resource(name)`
  - 读取资源对象。返回的 `ResourceSpec` 常用字段有：
  - `kind`：`pic` / `ocr` / `jmp`
  - `name`：资源变量名
  - `search_target`：图片文件名或 OCR 文本
  - `region`：识别区域
  - `confidence`：置信度
  - `jump_target`：`jmp` 资源对应的真实目标
  - `disable_grayscale`：图片资源是否禁用灰度匹配
- `ctx.get_jump_target(name)`
  - 读取某个 `jmp` 资源映射出来的真实跳转目标，但不立即跳转。
- `ctx.resolve_jump_target(target)`
  - 手动把标记或序号解析成当前流程里的真实下一步序号。
- `ctx.start_subflow(file_name)`
  - 直接启动一个普通子流程。若你只想“启动后继续下一步”，更推荐用 `self.start_subflow(...)`。
- `ctx.find_image(resource="...", name="...", region=..., confidence=..., grayscale=...)`
  - 查找图片。优先推荐传 `resource="资源变量名"`，这样图片名、区域、置信度都从资源文件读取。
  - 返回 `None` 表示未命中；命中时返回带 `x`、`y`、`center_x`、`center_y`、`width`、`height`、`confidence` 的对象。
- `ctx.find_text(resource="...", text="...", region=..., confidence=...)`
  - OCR 查找文本。推荐优先传 `resource="资源变量名"`。
  - 返回值规则与 `find_image` 一致。
- `ctx.screenshot(region=None)`
  - 获取当前截图。传 `region` 时会裁出对应区域并返回。
- `ctx.sleep(seconds)`
  - 脚本内等待指定秒数。
## 其他说明

- `pic` 与 `ocr` 操作在没有操作参数时，默认不断找图直到找到后将鼠标移至图片中心。
- `pic` 与 `ocr` 在使用 `exist` 或 `notExist` 后有两种配置     
   - 配置你要执行的 file.csv, 满足条件将会开启新的csv文件并执行，在执行完毕后会回到该csv并执行下一行，若不满足条件会继续执行下一行   
   - 配置 index;index，若满足条件则跳转到第一个目标，不满足则跳转到第二个目标；任一目标为负整数时立即结束当前流程，不再执行后续节点或等待时间
- `recovery.csv` 不是新的节点类型，而是一份普通 flow 文件；里面同样可以使用 `pic`、`ocr`、`jmp`、子流程和 `script`。

---
## 关于OCR版本
- 现在OCR版本分成了cpu和gpu版本,用不同后缀pyproject覆盖过去即可  
- GPU版本需要自行安装CUDA12.9和CUDNN并配置好环境变量
