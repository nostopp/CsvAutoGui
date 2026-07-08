import sys
if sys.platform == "win32":
    import pyscreeze
    from functools import partial
    pyscreeze.screenshot = partial(pyscreeze._screenshot_win32, allScreens=True)

from .scaleHelper import ScaleHelper
from .parser import GetCsv
from .ocr import OCR,PRINT_LOG
from .autoOperator import AutoOperator
from .screenshotMode import ScreenshotMode
from .baseInput import BaseInput
from .frontGroundInput import FrontGroundInput
from .backGroundInput import BackGroundInput
from .recordMode import RecordMode
from .notification_runtime import clear_thread_notifications, configure_thread_notifications
from .runtime_config import RuntimeConfigResolver
from .script_runtime import ScriptBase, ScriptContext, clear_script_cache
from .resource_loader import clear_resource_cache
from .recovery_runtime import run_config_with_watchdog
