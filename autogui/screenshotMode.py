import datetime
import time
import os
import keyboard
import pyautogui
import winsound
import win32con
import threading
from . import log

screenshotDir = 'screenshot'

class ScreenshotMode:
    def __init__(self):
        if not os.path.exists(screenshotDir):
            os.makedirs(screenshotDir)
        self._pressShotCount = 0
        self._lastShotPos = None
        # 捕获当前线程日志绑定（实例线程），用于在回调线程恢复
        self._log_binding = log.capture_binding()
        keyboard.add_hotkey('shift+x', log.wrap_callback(self.PressScreenshot, self._log_binding))

        self._pressMouseCount = 0
        self._lastMousePos = None
        keyboard.add_hotkey('shift+c', log.wrap_callback(self.PressMousePosition, self._log_binding))

        keyboard.add_hotkey('shift+f', log.wrap_callback(self.PressFullScreenshot, self._log_binding))

        log.info('shift+c 将打印当前鼠标位置\nshift+x 将记录先后两次鼠标位置并截图该区域\nshift+f 将进行全屏截图')

    def PressScreenshot(self):
        self._pressShotCount += 1
        pos = pyautogui.position()
        log.info(f'鼠标位置: {pos}')
        if self._pressShotCount >= 2:
            self.Screenshot(self._lastShotPos, pos)
            self._pressShotCount = 0
        self._lastShotPos = pos

    def PressFullScreenshot(self):
        try:
            import ctypes
        except:
            return
        pos1 = (ctypes.windll.user32.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN), ctypes.windll.user32.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN))
        pos2 = (ctypes.windll.user32.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN) + ctypes.windll.user32.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN), ctypes.windll.user32.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN) + ctypes.windll.user32.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN))
        self.Screenshot(pos1, pos2)

    def Screenshot(self, pos1, pos2):
        x1, y1 = pos1
        x2, y2 = pos2
        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        
        screenshot = pyautogui.screenshot(region=(left, top, width, height))

        time_str = datetime.datetime.now().strftime("%m%d%H%M%S")
        filename = f"{time_str}_{left};{top};{width};{height}.png"
        filepath = os.path.join(screenshotDir, filename)
        screenshot.save(filepath)

        threading.Thread(target=lambda: winsound.MessageBeep(winsound.MB_ICONHAND), daemon=True).start()
        log.info(f"截图已保存: {filepath}")

    def PressMousePosition(self):
        self._pressMouseCount += 1
        pos = pyautogui.position()
        log.info(f'鼠标位置: {pos}')
        if self._pressMouseCount >= 2:
            self._pressMouseCount = 0
            log.info(f'鼠标位置相差: {pos.x - self._lastMousePos.x}, {pos.y - self._lastMousePos.y}')
        self._lastMousePos = pos

    def Update(self):
        time.sleep(1)
        return True