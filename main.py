import argparse
import autogui
import autogui.autoOperator

LOOP = False
CONFIG_PATH = "config/test"

parser = argparse.ArgumentParser(description="自动化操作")
parser.add_argument("-p", "--path", type=str, help="运行配置路径", default=None)
parser.add_argument("-l", "--loop", action="store_true", help="是否循环")
args = parser.parse_args()

if args.path:
    CONFIG_PATH = args.path
if args.loop:
    LOOP = True if args.loop != 0 else False
print(f"工作路径: {CONFIG_PATH}, 是否循环: {LOOP}")

dataDict = autogui.parser.ParseCsv(CONFIG_PATH)
operator = autogui.AutoOperator(dataDict, CONFIG_PATH, LOOP)

while True:
    if not operator.Update():
        break