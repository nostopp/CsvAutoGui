### 使用说明
在config下新建文件夹并命名,在其中创建主配置main.csv,之后参考template及操作参数说明配置完毕后.python main.py -p config/文件夹名称 运行
| 运行参数 | 说明 | 默认值 |
| :-: | :-: | :-: |
| -p --path | 指定配置文件夹路径 | config/test |
| -l --loop| 自动化是否循环 | False |
| --log | 是否打印日志 | False |
| -s --screen | 运行在截图模式 | False |
| --scale | 运行分辨率与配置分辨率的比值 | 1 |
| --offset | 运行时对涉及到的绝对坐标进行偏移 | 0;0 |

ctrl+shift+x 终止程序运行
#### 截图模式
在该模式下按下 shift+x 将打印当前坐标,第二次按下将计算与第一次的坐标差值,并将两次坐标间的范围截图保存到screenshot目录下
在该模式下按下 shift+c 将打印当前坐标,第二次按下将计算与第一次的坐标差值,便于配置填写
在该模式下按下 shift+f 将进行全屏幕截图

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