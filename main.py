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
        mainOperator = autogui.MouseMode()
        while True:
            mainOperator.Update()
    else:
        subOperatorList : list[autogui.AutoOperator]= [] 
        mainOperator = autogui.AutoOperator(autogui.GetCsv(CONFIG_PATH), CONFIG_PATH, subOperatorList, LOOP, PRINT_LOG)

        while True:
            if len(subOperatorList) > 0 and not subOperatorList[-1].Update():
                subOperatorList.pop()
            elif not mainOperator.Update():
                break