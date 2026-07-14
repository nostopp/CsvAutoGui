"""CsvAutoGui runtime package initialization."""

import sys

if sys.platform == "win32":
    from functools import partial

    import pyscreeze

    pyscreeze.screenshot = partial(pyscreeze._screenshot_win32, allScreens=True)
