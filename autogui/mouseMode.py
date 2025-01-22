import time
import keyboard
import pyautogui

class MouseMode:
    def __init__(self):
        keyboard.on_release(self.onRelease)

    def onRelease(self, key):
        if key.name == 'space':
            pos = pyautogui.position()
            print(f'鼠标位置: {pos}')
        
    def Update(self):
        time.sleep(1)
        return True