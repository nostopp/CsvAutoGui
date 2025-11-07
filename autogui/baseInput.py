import numpy as np
from pyautogui import Point

PRIMARY = "left"
class BaseInput:
    def __init__(self, printLog=False):
        self._printLog = printLog
    def locateCenterOnScreen(self, image, **kwargs) -> Point:
        return Point(100, 100)
    def convertFindRegion(self, region):
        return region
    def screenShot(self):
        pass
    def hotkey(self, *args, **kwargs):
        pass
    def moveTo(self, x, y, duration=0.0):
        pass
    def moveRel(self, xOffset, yOffset, duration=None):
        pass
    def continueMoveTo(start:np.array, end:np.array, duration):
        pass
    def click(self, button=PRIMARY):
        pass
    def mouseDown(self, button=PRIMARY):
        pass
    def mouseUp(self, button=PRIMARY):
        pass
    def press(self, key):
        pass
    def keyDown(self, key):
        pass
    def keyUp(self, key):
        pass