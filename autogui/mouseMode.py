import time
import keyboard
import pyautogui

class MouseMode:
    def __init__(self):
        self._pressCount = 0
        self._lastPos = None
        keyboard.on_release(self.onRelease)

    def onRelease(self, key):
        if key.name == 'space':
            pos = pyautogui.position()
            print(f'鼠标位置: {pos}')

            self._pressCount += 1
            if self._pressCount >= 2:
                self._pressCount = 0
                print(f'鼠标位置相差: {pos.x - self._lastPos.x}, {pos.y - self._lastPos.y}')
            self._lastPos = pos
        
    def Update(self):
        time.sleep(1)
        return True