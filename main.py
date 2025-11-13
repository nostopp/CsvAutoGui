import argparse
import threading
import win32gui
import win32process
import psutil
import keyboard
import mouse
import autogui
from autogui import log


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="自动化操作")
    parser.add_argument("-c", "--config", type=str, help="运行配置路径", default="config/test")
    parser.add_argument("-l", "--loop", action="store_true", help="是否循环", default=False)
    parser.add_argument("--log", action="store_true", help="是否打印日志", default=False)
    parser.add_argument("-s", "--screenshots", action="store_true", help="截图模式", default=False)
    parser.add_argument("--scale", help="与配置所用分辨率的缩放值", default=1.0, type=float)
    parser.add_argument("--scale_image", help="缩放时是否缩放用到的截图", default=False, type=bool)
    parser.add_argument("--offset", help="搜索时需要的偏移值", default="0;0", type=str)
    parser.add_argument("-t", "--title", help="目标窗口名称,指定后程序运行在后台窗口模式", default=None, type=str)
    parser.add_argument("-m", "--multi_window", action="store_true", help="后台窗口多窗口控件模式", default=False)
    parser.add_argument("--process", action="store_true", help="获取所有可见窗口名称", default=False)
    parser.add_argument("--record", action="store_true", help="录制鼠标和键盘事件并导出 CSV", default=False)
    # internal flag to indicate called from GUI manager
    parser.add_argument("--_from_window", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def getProcessName(log=print):
    def list_all_windows():
        windows = []

        def callback(hwnd, windows_list):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:  # 只显示有标题的窗口
                    class_name = win32gui.GetClassName(hwnd)
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process_name = ""
                    try:
                        if pid > 0:
                            process = psutil.Process(pid)
                            process_name = process.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        process_name = "Unknown"
                    windows_list.append({
                        'hwnd': hwnd,
                        'title': title,
                        'process': process_name,
                        'pid': pid,
                        'class_name': class_name,
                    })
            return True

        win32gui.EnumWindows(callback, windows)
        return windows

    # 列出所有可见窗口
    all_windows = list_all_windows()
    for window in all_windows:
        log(f"HWND: {window['hwnd']}, PID: {window['pid']}, CLASS: {window['class_name']}, 进程: {window['process']}, 标题: '{window['title']}'")

    cur_pos = win32gui.GetCursorPos()
    cur_hwnd = win32gui.WindowFromPoint(cur_pos)
    _, pid = win32process.GetWindowThreadProcessId(cur_hwnd)
    title = win32gui.GetWindowText(cur_hwnd)
    class_name = win32gui.GetClassName(cur_hwnd)
    process_name = ""
    try:
        if pid > 0:
            process = psutil.Process(pid)
            process_name = process.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        process_name = "Unknown"
    log(f"当前鼠标位置 HWND: {cur_hwnd}, PID: {pid}, CLASS: {class_name}, 进程: {process_name}, 标题: '{title}'")


def start_instance(args: argparse.Namespace, log_callback=print, stop_event: threading.Event = None, use_hotkey: bool = True):
    """
    在当前进程中启动一个 main 实例（多实例支持），不使用全局 KEEP_RUN。
    - args: argparse.Namespace（与 parse_args 返回格式一致）
    - log_callback: 可调用对象，接收字符串，用于显示日志
    - stop_event: threading.Event，用来停止运行；如果 None，会创建一个本地事件并在 hotkey 时设置
    - use_hotkey: 是否注册 Shift+Ctrl+X 退出（仅用于命令行启动）
    """
    try:
        # 将当前实例名（config 路径）放入线程上下文，方便日志带上来源
        log.set_thread_context({'name': args.config})
        if log_callback and log_callback is not print:
            # 使用线程级 handler，避免多个实例互相覆盖全局 handler
            log.set_thread_handler(log_callback)
        else:
            # CLI 默认行为仍为 print（不设置线程 handler）
            log.reset_thread_handler()
    except Exception as e:
        log_callback(f"设置日志处理器失败: {e}")

    CONFIG_PATH = args.config
    LOOP = args.loop
    PRINT_LOG = args.log
    SCREENSHOT_MODE = args.screenshots
    GET_PROCESS = args.process
    TITLE = args.title
    MULTI_WINDOW = args.multi_window
    RECORD = args.record

    log.debug(f"工作路径: {CONFIG_PATH}, 是否循环: {LOOP}, 是否打印日志: {PRINT_LOG}, 截图模式: {SCREENSHOT_MODE}")

    # 初始化 scale helper 等
    try:
        scale_helper = autogui.ScaleHelper()
        scale_helper.Init(args.scale, args.offset, args.scale_image)
        # autogui.ScaleHelper.Instance().Init(args.scale, args.offset, args.scale_image)
    except Exception as e:
        log.error(f"ScaleHelper init 失败: {e}")

    if autogui.backGroundInput.SAVE_SCREENSHOT:
        autogui.backGroundInput.SAVE_SCREENSHOT_PATH = CONFIG_PATH
    if autogui.ocr.SAVE_OCR_FILE:
        autogui.ocr.OCR_FILE_PATH = CONFIG_PATH
    autogui.ocr._thread_local.PRINT_LOG = PRINT_LOG

    if GET_PROCESS:
        getProcessName(log_callback)
        return

    local_stop = stop_event or threading.Event()

    if use_hotkey:
        # 仅在交互式命令行时绑定全局热键
        def _exit():
            local_stop.set()
        try:
            keyboard.add_hotkey('shift+ctrl+x', _exit)
            log_callback("按下 Shift + Ctrl + X 退出程序")
        except Exception as e:
            log_callback(f"注册热键失败: {e}")

    try:
        if SCREENSHOT_MODE:
            mainOperator = autogui.ScreenshotMode()
            while not local_stop.is_set():
                mainOperator.Update()
        elif RECORD:
            mainOperator = autogui.RecordMode()
            while not local_stop.is_set():
                mainOperator.Update()
        else:
            if not TITLE:
                input_obj = autogui.FrontGroundInput(PRINT_LOG)
            else:
                input_obj = autogui.BackGroundInput(TITLE, MULTI_WINDOW, PRINT_LOG)

            subOperatorList: list[autogui.AutoOperator] = []
            mainOperator = autogui.AutoOperator(autogui.GetCsv(CONFIG_PATH, scale_helper), CONFIG_PATH, subOperatorList, input_obj, scale_helper, LOOP, PRINT_LOG)

            while not local_stop.is_set():
                if len(subOperatorList) > 0:
                    if not subOperatorList[-1].Update():
                        subOperatorList.pop()
                else:
                    if not mainOperator.Update():
                        break
    except Exception as e:
        log.error(f"运行时抛出异常: {e}")
    finally:
        if RECORD:
            keyboard.remove_hotkey('shift+x')
        elif SCREENSHOT_MODE:
            keyboard.remove_hotkey('shift+x')
            keyboard.remove_hotkey('shift+c')
            keyboard.remove_hotkey('shift+f')
        # 在 GUI 管理多实例时避免直接 unhook 全局鼠标键盘
        if use_hotkey:
            try:
                mouse.unhook_all()
            except Exception:
                pass
            try:
                keyboard.unhook_all()
            except Exception:
                pass
        # 恢复日志模块的上下文与 handler
        try:
            log.clear_thread_context()
            log.reset_thread_handler()
        except Exception:
            pass


if __name__ == "__main__":
    # 保持命令行行为：解析 args 并以阻塞方式运行
    args = parse_args()
    # 当命令行启动时，启用 hotkey，使用主线程阻塞运行
    start_instance(args, log_callback=print, stop_event=None, use_hotkey=True)