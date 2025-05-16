import sys
if sys.platform == "win32":
    import pyscreeze
    from functools import partial
    pyscreeze.screenshot = partial(pyscreeze._screenshot_win32, allScreens=True)

from .parser import GetCsv
from .ocr import OCR
from .autoOperator import AutoOperator
from .screenshotMode import ScreenshotMode