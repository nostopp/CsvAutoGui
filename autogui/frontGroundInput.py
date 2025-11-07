import time
import pyautogui
import pydirectinput
import numpy as np
import cv2
from .baseInput import BaseInput

MOVE_FPS = 60
MOVE_INTERVAL = 1/MOVE_FPS
PRIMARY = "left"
class FrontGroundInput(BaseInput):
    def __init__(self, printLog=False):
        self._printLog = printLog

    def locateCenterOnScreen(self, image, **kwargs):
        return pyautogui.locateCenterOnScreen(image, **kwargs)

    def screenShot(self):
        screenShot = pyautogui.screenshot()
        img = np.array(screenShot)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def hotkey(self, *args, **kwargs):
        pyautogui.hotkey(*args, **kwargs)

    def moveTo(self, x, y, duration=0.0):
        if not duration:
            pydirectinput.moveTo(x, y, _pause=False)
            return

        start = np.array(pydirectinput.position())
        end = np.array([x, y])
        self.continueMoveTo(start, end, duration)

    def moveRel(self, xOffset, yOffset, duration=None):
        if not duration:
            pydirectinput.moveRel(xOffset, yOffset, _pause=False)
            return

        start = np.array(pydirectinput.position())
        end = start + np.array([xOffset, yOffset])
        self.continueMoveTo(start, end, duration)

    def continueMoveTo(start:np.array, end:np.array, duration):
        steps = max(1, int(duration * MOVE_FPS))
        delta = end - start
        start_time = time.perf_counter()
        for i in range(steps):
            t = (i + 1) / steps
            x = int(start[0] + delta[0] * t)
            y = int(start[1] + delta[1] * t)
            pydirectinput.moveTo(x, y, _pause=False)
            next_frame_time = start_time + (i + 1) * MOVE_INTERVAL
            now = time.perf_counter()
            sleep_time = next_frame_time - now
            if sleep_time > 0:
                time.sleep(sleep_time)
        # 最后确保到达终点
        # pydirectinput.moveTo(int(end[0]), int(end[1]), _pause=False)

    def click(self, button=PRIMARY):
        pydirectinput.click(button=button, _pause=False)

    def mouseDown(self, button=PRIMARY):
        pydirectinput.mouseDown(button=button, _pause=False)

    def mouseUp(self, button=PRIMARY):
        pydirectinput.mouseUp(button=button, _pause=False)

    def press(self, key):
        pydirectinput.press(key, _pause=False)

    def keyDown(self, key):
        pydirectinput.keyDown(key, _pause=False)

    def keyUp(self, key):
        pydirectinput.keyUp(key, _pause=False)