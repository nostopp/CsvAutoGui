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

### 运行参数

| 参数 | 说明 | 默认值 |
| :-: | :-: | :-: |
| -p / --path | 指定配置文件夹路径 | config/test |
| -l / --loop | 自动化是否循环 | False |
| --log | 是否打印日志 | False |
| -s / --screen | 运行在截图模式 | False |
| --record | 运行在记录操作模式 | False |
| --scale | 运行分辨率与配置分辨率的比值 | 1 |
| --scale_image | 缩放时是否缩放用到的截图 | False |
| --offset | 运行时对涉及到的绝对坐标进行偏移 | 0;0 |
| -t / --title | 目标窗口名称,指定后程序运行在后台窗口模式 | None |
| -m / --multi_window | 后台窗口多窗口控件模式 | False |
| --process | 获取所有可见窗口名称 | False |

- **终止程序**：按 `Ctrl+Shift+X`

---

## 截图模式

- 按下 `Shift+X`：打印当前坐标，第二次按下将计算与第一次的坐标差值，并将两次坐标间的范围截图保存到 `screenshot` 目录下。
- 按下 `Shift+C`：打印当前坐标，第二次按下将计算与第一次的坐标差值，便于配置填写。
- 按下 `Shift+F`：进行全屏幕截图。

---

## 记录操作模式

- 按下 `Shift+X`：开始记录操作
- 再次按下 `Shift+X`：停止记录操作,并将操作保存在record目录

---

## CSV 各列说明

| 列 | 说明 | 示例（/分开代表不同示例） |
| :-: | :-: | :-: |
| 序号 | 操作会按序号顺序执行，需保证序号从 1 递增 | 1 |
| 操作 | 本次执行的操作，具体内容见下表 | pic |
| 操作参数 | 本次操作的参数，具体内容见下表 | test.png |
| 完成后等待时间 | 操作完成后的等待时间，分号可加入随机等待时间 | 2 / 2;0.5 |
| 图片/ocr名称 | `pic` 操作时图片名称（需带后缀，放在配置文件同目录）；`ocr` 操作时要识别的目标文字。若为纯数字，支持比较大小（<; <=; >; >=; ==; !=;） | test.png / 需识别文字,数字比对<=;1000 |
| 图片/ocr坐标范围 | `pic` 或 `ocr` 操作时识别的屏幕坐标范围，格式为 `起始点x;起始点y;宽;高`，可用截图模式快速定位 | 0;0;1920;1080 |
| 图片/ocr置信度 | `pic` 或 `ocr` 操作时的识别置信度（0-1） | 0.8 |
| 未找到图片/ocr重试时间 | 未找到目标时且未配置 notExist 参数时的重试时间，支持分号加入随机延迟 | 1 / 1;0.5 |
| 图片/ocr定位移动随机 | 搜索到目标且未使用 exist 等参数时，移动到图片范围中的随机位置 | 1 |
| 移动操作用时 | `mMove` `mMoveTo` `pic` `ocr` 等各种涉及到鼠标移动操作时可控制移动到目标点的用时 | 1 |
| 跳转标记 | `pic` `ocr` 等涉及到跳转的操作参数时可用的跳转标记 | tap |
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
| pic | exist;fileName.csv / notExist;fileName.csv / exist;index;index / notExist;index;index | 识图 |
| ocr | exist;fileName.csv / notExist;fileName.csv / exist;index;index / notExist;index;index | OCR 识别 |
| notify | text | 通知 |

---

## 其他说明

- `pic` 与 `ocr` 操作在没有操作参数时，默认不断找图直到找到后将鼠标移至图片中心。
- `pic` 与 `ocr` 在使用 `exist` 或 `notExist` 后有两种配置     
   - 配置你要执行的 file.csv, 满足条件将会开启新的csv文件并执行，在执行完毕后会回到该csv并执行下一行，若不满足条件会继续执行下一行   
   - 配置 int;int,若满足条件则跳转到第一个int配置的序号步骤，不满足则跳转到第二个int配置的步骤序号

---
## 关于OCR版本
- 现在OCR版本分成了cpu和gpu版本,用不同后缀pyproject覆盖过去即可  
- GPU版本需要自行安装CUDA12.9和CUDNN并配置好环境变量