import argparse
import keyboard
import autogui

parser = argparse.ArgumentParser(description="自动化操作")
parser.add_argument("-c", "--config", type=str, help="运行配置路径", default="config/test")
parser.add_argument("-l", "--loop", action="store_true", help="是否循环", default=False)
parser.add_argument("--log", action="store_true", help="是否打印日志", default=False)
parser.add_argument("-s", "--screenshots", action="store_true", help="截图模式", default=False)
parser.add_argument("--scale", help="与配置所用分辨率的缩放值", default=1.0, type=float)
parser.add_argument("--scale_image", help="缩放时是否缩放用到的截图", default=False, type=bool)
parser.add_argument("--offset", help="搜索时需要的偏移值", default="0;0", type=str)
parser.add_argument("-t", "--title", help="目标窗口名称", default=None, type=str)
parser.add_argument("--process", action="store_true", help="获取所有可见窗口名称", default=False)
args = parser.parse_args()

CONFIG_PATH = args.config
LOOP = args.loop
PRINT_LOG = args.log
SCREENSHOT_MODE = args.screenshots
GET_PROCESS = args.process
TITLE = args.title
print(f"工作路径: {CONFIG_PATH}, 是否循环: {LOOP}, 是否打印日志: {PRINT_LOG}, 截图模式: {args.screenshots}")

autogui.ScaleHelper.Instance().Init(args.scale, args.offset, args.scale_image)

if autogui.backGroundInput.SAVE_SCREENSHOT:
    autogui.backGroundInput.SAVE_SCREENSHOT_PATH = CONFIG_PATH
if autogui.ocr.SAVE_OCR_FILE:
    autogui.ocr.OCR_FILE_PATH = CONFIG_PATH

def getProcessName():
    import win32gui
    import win32process
    def list_all_windows():
        windows = []
    
        def callback(hwnd, windows_list):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:  # 只显示有标题的窗口
                    class_name = win32gui.GetClassName(hwnd)
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    windows_list.append({
                        'hwnd': hwnd,
                        'title': title,
                        'class': class_name,
                        'pid': pid
                    })
            return True
    
        win32gui.EnumWindows(callback, windows)
        return windows

    # 列出所有可见窗口
    all_windows = list_all_windows()
    for window in all_windows:
        print(f"HWND: {window['hwnd']}, PID: {window['pid']}, 类名: {window['class']}, 标题: '{window['title']}'")

def main():
    if GET_PROCESS:
        getProcessName()
        return

    KEEP_RUN = True
    def exit():
        global KEEP_RUN
        KEEP_RUN = False
    keyboard.add_hotkey('shift+ctrl+x', exit)
    print("按下 Shift + Ctrl + X 退出程序")

    if SCREENSHOT_MODE:
        mainOperator = autogui.ScreenshotMode()
        while KEEP_RUN:
            mainOperator.Update()
    else:
        if not TITLE:
            input = autogui.FrontGroundInput()
        else:
            input = autogui.BackGroundInput(TITLE)
        
        subOperatorList : list[autogui.AutoOperator]= [] 
        mainOperator = autogui.AutoOperator(autogui.GetCsv(CONFIG_PATH), CONFIG_PATH, subOperatorList, input, LOOP, PRINT_LOG)

        while KEEP_RUN:
            if len(subOperatorList) > 0:
                if not subOperatorList[-1].Update():
                    subOperatorList.pop()
            else:
                if not mainOperator.Update():
                    break

    keyboard.unhook_all()

if __name__ == "__main__":
    main()