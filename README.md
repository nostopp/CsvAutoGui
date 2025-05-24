本项目通过配置csv来进行一些自动化操作

### 使用说明
本项目使用uv管理,需安装[uv](https://docs.astral.sh/uv/)
在config下新建文件夹并命名,在其中创建主配置main.csv,之后参考template及example配置完毕后(example图片名格式皆为用自带截图模式截图,图片仅保留一个示意).uv run main.py -c config/文件夹名称 运行
| 运行参数 | 说明 | 默认值 |
| :-: | :-: | :-: |
| -p --path | 指定配置文件夹路径 | config/test |
| -l --loop| 自动化是否循环 | False |
| --log | 是否打印日志 | False |
| -s --screen | 运行在截图模式 | False |
| --scale | 运行分辨率与配置分辨率的比值 | 1 |
| --scale_image | 缩放时是否缩放用到的截图 | False |
| --offset | 运行时对涉及到的绝对坐标进行偏移 | 0;0 |

ctrl+shift+x 终止程序运行
#### 截图模式
在该模式下按下 shift+x 将打印当前坐标,第二次按下将计算与第一次的坐标差值,并将两次坐标间的范围截图保存到screenshot目录下
在该模式下按下 shift+c 将打印当前坐标,第二次按下将计算与第一次的坐标差值,便于配置填写
在该模式下按下 shift+f 将进行全屏幕截图

### csv各列说明
| 列 | 说明 | 示例(/分开代表不同示例) |
| :-: | :-: | :-: |
| 序号 | 操作会按序号顺序执行,需要保证序号从1递增 | 1 |
| 操作 | 此次执行的操作,具体操作内容见下 | pic |
| 操作参数 | 此次执行的操作的一些参数,具体操作内容见下 | test.png |
| 完成后等待时间 | 完成操作后的等待时间,使用分号可加入随机等待时间 | 2 / 2;0.5 |
| 图片/ocr名称 | pic操作时图片名称(需要后缀名,放置在配置文件同目录) 或 ocr操作时要识别的目标文字 | test.png / 需识别文字 |
| 图片/ocr坐标范围 | pic操作或ocr操作时识别的屏幕坐标范围,格式为 起始点x;起始点y;宽;高,限定识别范围可有效加速识别,范围可配置脚本截图模式快速定位 | 例如1080p全屏幕0;0;1920;1080 |
| 图片/ocr置信度 | pic操作或ocr操作时的识别置信度(0-1) | 0.8 |
| 未找到图片/ocr重试时间 | pic操作或ocr操作时未找到目标时且未配置notExist参数时的重试时间,若配置了将会覆盖上面的完成等待时间,同样支持;加入随机延迟 | 1 / 1;0.5 |

### 操作
| 操作名称 | 操作参数 | 说明 |
| :-: | :-: | :-: |
|click| left or middle or right | 鼠标点击 |
|mDown| left or middle or right | 鼠标按下 |
|mUp| left or middle or right | 鼠标松开 |
|mMove| xOffset;yOffset | 鼠标相对坐标移动(参数必须) |
|mMoveTo| xOffset;yOffset | 鼠标绝对坐标移动(参数必须) |
|press| key | 键盘按键(参数必须) |
|kDown| key | 键盘按键按下(参数必须) |
|kUp| key | 键盘按键松开(参数必须) |
|write| text | 键盘输入(参数必须) |
|pic| exist;fileName.csv or notExist;fileName.csv  | 识图 |
|ocr| exist;fileName.csv or notExist;fileName.csv  | ocr |
|end|   | 终止该csv的继续执行 |

#### 一些说明
* pic与ocr操作在没有操作参数时默认不断找图直到找到后将鼠标移至图片中心
* pic与ocr在使用exist或者notExist后不满足条件将执行下一步不会持续找图,满足条件将会启动新的csv,执行完毕将重新执行此步