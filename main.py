import argparse
import autogui
import autogui.autoOperator

parser = argparse.ArgumentParser(description="自动化操作")
parser.add_argument("-p", "--path", type=str, help="运行配置路径", default="config/test")
parser.add_argument("-l", "--loop", action="store_true", help="是否循环", default=False)
parser.add_argument("--log", action="store_true", help="是否打印日志", default=False)
parser.add_argument("--mouse", action="store_true", help="打印鼠标位置模式", default=False)
args = parser.parse_args()

CONFIG_PATH = args.path
LOOP = args.loop
PRINT_LOG = args.log
MOUSE_MODE = args.mouse
print(f"工作路径: {CONFIG_PATH}, 是否循环: {LOOP}, 是否打印日志: {PRINT_LOG}, 打印鼠标位置模式: {MOUSE_MODE}")

if __name__ == "__main__":
    if MOUSE_MODE:
        operator = autogui.MouseMode()
        while True:
            operator.Update()
    else:
        dataDict = autogui.parser.ParseCsv(CONFIG_PATH)
        operator = autogui.AutoOperator(dataDict, CONFIG_PATH, LOOP, PRINT_LOG)

        while True:
            if not operator.Update():
                break