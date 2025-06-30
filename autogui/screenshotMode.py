import datetime
import time
import os
import keyboard
import pyautogui
import winsound

screenshotDir = 'screenshot'

class ScreenshotMode:
    def __init__(self):
        if not os.path.exists(screenshotDir):
            os.makedirs(screenshotDir)
        self._pressShotCount = 0
        self._lastShotPos = None
        keyboard.add_hotkey('shift+x', self.PressScreenshot)

        self._pressMouseCount = 0
        self._lastMousePos = None
        keyboard.add_hotkey('shift+c', self.PressMousePosition)

        keyboard.add_hotkey('shift+f', self.PressFullScreenshot)

        print('shift+x 将打印当前坐标\nshift+c 将打印当前鼠标位置\nshift+f 将进行全屏截图')

    def PressScreenshot(self):
        self._pressShotCount += 1
        pos = pyautogui.position()
        print(f'鼠标位置: {pos}')
        if self._pressShotCount >= 2:
            self.Screenshot(self._lastShotPos, pos)
            self._pressShotCount = 0
        self._lastShotPos = pos

    def PressFullScreenshot(self):
        try:
            import ctypes
        except:
            return
        pos1 = (ctypes.windll.user32.GetSystemMetrics(76), ctypes.windll.user32.GetSystemMetrics(77))
        pos2 = (ctypes.windll.user32.GetSystemMetrics(76) + ctypes.windll.user32.GetSystemMetrics(78), ctypes.windll.user32.GetSystemMetrics(77) + ctypes.windll.user32.GetSystemMetrics(79))
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

        try:
            winsound.Beep(200, 100)
        except:
            pass
        print(f"截图已保存: {filepath}")

    def PressMousePosition(self):
        self._pressMouseCount += 1
        pos = pyautogui.position()
        print(f'鼠标位置: {pos}')
        if self._pressMouseCount >= 2:
            self._pressMouseCount = 0
            print(f'鼠标位置相差: {pos.x - self._lastMousePos.x}, {pos.y - self._lastMousePos.y}')
        self._lastMousePos = pos

    def Update(self):
        time.sleep(1)
        return True