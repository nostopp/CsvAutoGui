import sys
if sys.platform == "win32":
    import pyscreeze
    from functools import partial
    pyscreeze.screenshot = partial(pyscreeze._screenshot_win32, allScreens=True)

from .scaleHelper import ScaleHelper
from .parser import GetCsv
from .ocr import OCR
from .autoOperator import AutoOperator
from .screenshotMode import ScreenshotMode
from .baseInput import BaseInput
from .frontGroundInput import FrontGroundInput
from .backGroundInput import BackGroundInput