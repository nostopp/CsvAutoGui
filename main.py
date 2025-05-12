import argparse
import keyboard
import autogui

parser = argparse.ArgumentParser(description="自动化操作")
parser.add_argument("-c", "--config", type=str, help="运行配置路径", default="config/test")
parser.add_argument("-l", "--loop", action="store_true", help="是否循环", default=False)
parser.add_argument("--log", action="store_true", help="是否打印日志", default=False)
parser.add_argument("-s", "--screenshots", action="store_true", help="截图模式", default=False)
args = parser.parse_args()

CONFIG_PATH = args.config
LOOP = args.loop
PRINT_LOG = args.log
SCREENSHOT_MODE = args.screenshots
print(f"工作路径: {CONFIG_PATH}, 是否循环: {LOOP}, 是否打印日志: {PRINT_LOG}, 截图模式: {args.screenshots}")

if autogui.ocr.SAVE_OCR_FILE:
    autogui.ocr.OCR_FILE_PATH = CONFIG_PATH

if __name__ == "__main__":
    KEEP_RUN = True
    def exit():
        global KEEP_RUN
        KEEP_RUN = False
    keyboard.add_hotkey('shift+ctrl+x', exit)

    if SCREENSHOT_MODE:
        mainOperator = autogui.ScreenshotMode()
        while KEEP_RUN:
            mainOperator.Update()
    else:
        subOperatorList : list[autogui.AutoOperator]= [] 
        mainOperator = autogui.AutoOperator(autogui.GetCsv(CONFIG_PATH), CONFIG_PATH, subOperatorList, LOOP, PRINT_LOG)

        while KEEP_RUN:
            if len(subOperatorList) > 0:
                if not subOperatorList[-1].Update():
                    subOperatorList.pop()
            else:
                if not mainOperator.Update():
                    break