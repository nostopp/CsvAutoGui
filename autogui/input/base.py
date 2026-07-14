import numpy as np
from pyautogui import Point

PRIMARY = "left"


class BaseInput:
    def __init__(self, printLog: bool = False):
        self._printLog = printLog

    def locateCenterOnScreen(self, image, **kwargs) -> Point:
        return Point(100, 100)

    def convertFindRegion(self, region):
        return region

    def screenShot(self):
        pass

    def hotkey(self, *args, **kwargs) -> None:
        pass

    def moveTo(self, x, y, duration=0.0) -> None:
        pass

    def moveRel(self, xOffset, yOffset, duration=None) -> None:
        pass

    def continueMoveTo(self, start: np.array, end: np.array, duration):
        pass

    def click(self, button=PRIMARY) -> None:
        pass

    def mouseDown(self, button=PRIMARY) -> None:
        pass

    def mouseUp(self, button=PRIMARY) -> None:
        pass

    def press(self, key) -> None:
        pass

    def keyDown(self, key) -> None:
        pass

    def keyUp(self, key) -> None:
        pass

    def record_observation(self, detail: str, source: str = "script_ctx") -> None:
        pass
