import datetime
import time
import os
import keyboard
import pyautogui

screenshotDir = 'screenshot'

class ScreenshotMode:
    def __init__(self):
        if not os.path.exists(screenshotDir):
            os.makedirs(screenshotDir)
        self._pressCount = 0
        self._lastPos = None
        keyboard.add_hotkey('shift+x', self.PressScreenshot)

    def PressScreenshot(self):
        self._pressCount += 1
        pos = pyautogui.position()
        print(f'鼠标位置: {pos}')
        if self._pressCount >= 2:
            self.Screenshot(self._lastPos, pos)
            self._pressCount = 0
        self._lastPos = pos

    def Screenshot(self, pos1, pos2):
        x1, y1 = pos1
        x2, y2 = pos2
        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        
        screenshot = pyautogui.screenshot(region=(left, top, width, height))

        time_str = datetime.datetime.now().strftime("%m%d%H%M%S")
        filename = f"{left};{top};{width};{height}_{time_str}.png"
        filepath = os.path.join(screenshotDir, filename)
        screenshot.save(filepath)
        print(f"截图已保存: {filepath}")

    def Update(self):
        time.sleep(1)
        return True