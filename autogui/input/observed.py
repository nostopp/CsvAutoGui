from ..execution.watchdog import ExecutionWatchdog
from .base import BaseInput


class ObservedInput(BaseInput):
    def __init__(self, inner: BaseInput, watchdog: ExecutionWatchdog) -> None:
        super().__init__(getattr(inner, "_printLog", False))
        self._inner = inner
        self._watchdog = watchdog

    def record_observation(self, detail: str, source: str = "script_ctx") -> None:
        self._watchdog.record_observation(detail, source=source)

    def locateCenterOnScreen(self, image, **kwargs):
        return self._inner.locateCenterOnScreen(image, **kwargs)

    def convertFindRegion(self, region):
        return self._inner.convertFindRegion(region)

    def screenShot(self):
        return self._inner.screenShot()

    def hotkey(self, *args, **kwargs) -> None:
        self._inner.hotkey(*args, **kwargs)
        self._watchdog.record_progress("hotkey", source="input")

    def moveTo(self, x, y, duration=0.0) -> None:
        self._inner.moveTo(x, y, duration)

    def moveRel(self, xOffset, yOffset, duration=None) -> None:
        self._inner.moveRel(xOffset, yOffset, duration)

    def continueMoveTo(self, start, end, duration):
        return self._inner.continueMoveTo(start, end, duration)

    def click(self, button="left") -> None:
        self._inner.click(button=button)
        self._watchdog.record_progress("click", source="input")

    def mouseDown(self, button="left") -> None:
        self._inner.mouseDown(button=button)
        self._watchdog.record_progress("mouseDown", source="input")

    def mouseUp(self, button="left") -> None:
        self._inner.mouseUp(button=button)
        self._watchdog.record_progress("mouseUp", source="input")

    def press(self, key) -> None:
        self._inner.press(key)
        self._watchdog.record_progress("press", source="input")

    def keyDown(self, key) -> None:
        self._inner.keyDown(key)
        self._watchdog.record_progress("keyDown", source="input")

    def keyUp(self, key) -> None:
        self._inner.keyUp(key)
        self._watchdog.record_progress("keyUp", source="input")

    def __getattr__(self, name: str):
        return getattr(self._inner, name)
