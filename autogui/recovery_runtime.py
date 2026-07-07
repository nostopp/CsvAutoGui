import datetime
import traceback
import ctypes
from dataclasses import dataclass
from pathlib import Path
import re
from threading import Event
from typing import Any

import pyautogui
import win32con

from . import log
from .autoOperator import AutoOperator
from .baseInput import BaseInput
from .execution_watchdog import ExecutionWatchdog
from .observed_input import ObservedInput
from .parser import GetCsv
from .runtime_config import RuntimeConfigResolver, WatchdogSettings, WatchdogThresholds
from .scaleHelper import ScaleHelper


NON_PROGRESS_OPERATIONS = {"mMove", "mMoveTo", "pic", "ocr", "jmp", "notify", "script"}
RECOVERY_SCREENSHOT_DIR = Path("screenshot")
_FILENAME_SANITIZE_PATTERN = re.compile(r'[<>:"/\\|?*\s]+')


@dataclass(frozen=True)
class StepInfo:
    flow_name: str
    index: int
    operate: str


@dataclass(frozen=True)
class SessionRunResult:
    status: str
    step: StepInfo | None = None


class FlowRuntimeSession:
    def __init__(
        self,
        config_dir: str,
        source_file: str,
        input_obj: BaseInput,
        scale_helper: ScaleHelper,
        loop: bool,
        print_log: bool,
        shared_state: dict[str, Any] | None = None,
    ) -> None:
        shared_state = {} if shared_state is None else shared_state
        self.sub_operator_list: list[AutoOperator] = []
        self.main_operator = AutoOperator(
            GetCsv(config_dir, scale_helper, source_file),
            config_dir,
            self.sub_operator_list,
            input_obj,
            scale_helper,
            loop,
            print_log,
            shared_state,
            sourceFile=source_file,
        )
        self.main_finished = False

    def get_active_operator(self) -> AutoOperator | None:
        if self.sub_operator_list:
            return self.sub_operator_list[-1]
        if self.main_finished:
            return None
        return self.main_operator

    def peek_current_step(self) -> StepInfo | None:
        operator = self.get_active_operator()
        if operator is None:
            return None
        operation = operator.peek_current_operation()
        return StepInfo(operator.source_file, operation["index"], operation["operate"])

    def step(self) -> bool:
        if self.sub_operator_list:
            idx = len(self.sub_operator_list) - 1
            sub_operator = self.sub_operator_list[idx]
            if not sub_operator.Update():
                self.sub_operator_list.pop(idx)
            return True

        if self.main_finished:
            return False

        if not self.main_operator.Update():
            self.main_finished = True
            return False

        return True


def _run_session_until_boundary(
    session: FlowRuntimeSession,
    watchdog: ExecutionWatchdog,
    stop_event: Event,
) -> SessionRunResult:
    while not stop_event.is_set():
        step = session.peek_current_step()
        if step is None:
            return SessionRunResult("finished", None)

        watchdog.begin_step()
        has_more = session.step()
        if not watchdog.current_step_had_progress and step.operate in NON_PROGRESS_OPERATIONS:
            watchdog.record_observation(step.operate, source="node")

        if watchdog.should_recover():
            return SessionRunResult("stalled", step)

        if not has_more and not session.sub_operator_list:
            return SessionRunResult("finished", step)

    return SessionRunResult("stopped")


def _sanitize_filename_part(value: str) -> str:
    sanitized = _FILENAME_SANITIZE_PATTERN.sub("_", value.strip())
    sanitized = sanitized.strip("._")
    return sanitized or "unknown"


def capture_recovery_screenshot(config_dir: str, step: StepInfo | None) -> Path | None:
    try:
        left = ctypes.windll.user32.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        top = ctypes.windll.user32.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        width = ctypes.windll.user32.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
        height = ctypes.windll.user32.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
        screenshot = pyautogui.screenshot(region=(left, top, width, height))
        RECOVERY_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        config_name = _sanitize_filename_part(Path(config_dir).name)
        flow_name = _sanitize_filename_part(step.flow_name if step is not None else "unknown_flow")
        index = "unknown" if step is None else str(step.index)
        output_path = RECOVERY_SCREENSHOT_DIR / f"recovery_{config_name}_{flow_name}_{index}_{timestamp}.png"
        screenshot.save(output_path)
        return output_path
    except Exception:
        log.error(f"保存 recovery 全屏截图失败\n{traceback.format_exc()}")
        return None


def create_main_session(
    config_dir: str,
    real_input: BaseInput,
    scale_helper: ScaleHelper,
    loop: bool,
    print_log: bool,
    watchdog_settings: WatchdogSettings,
    recovery_count: int,
) -> tuple[FlowRuntimeSession, ExecutionWatchdog]:
    watchdog = ExecutionWatchdog(
        watchdog_settings.stall_timeout_seconds,
        watchdog_settings.stall_non_progress_ops,
    )
    observed_input = ObservedInput(real_input, watchdog)
    session = FlowRuntimeSession(
        config_dir=config_dir,
        source_file="main.csv",
        input_obj=observed_input,
        scale_helper=scale_helper,
        loop=loop,
        print_log=print_log,
    )
    return session, watchdog


def run_recovery_flow(
    config_dir: str,
    real_input: BaseInput,
    scale_helper: ScaleHelper,
    print_log: bool,
    runtime_resolver: RuntimeConfigResolver,
    stop_event: Event,
    recovery_count: int,
) -> tuple[bool, str]:
    thresholds: WatchdogThresholds = runtime_resolver.get_recovery_watchdog_thresholds()
    watchdog = ExecutionWatchdog(
        thresholds.stall_timeout_seconds,
        thresholds.stall_non_progress_ops,
    )
    observed_input = ObservedInput(real_input, watchdog)
    session = FlowRuntimeSession(
        config_dir=config_dir,
        source_file="recovery.csv",
        input_obj=observed_input,
        scale_helper=scale_helper,
        loop=False,
        print_log=print_log,
    )
    try:
        result = _run_session_until_boundary(session, watchdog, stop_event)
    except Exception:
        log.error(f"执行 recovery.csv 失败\n{traceback.format_exc()}")
        return False, "recovery.csv 抛出异常"
    if result.status == "finished":
        return True, "recovery.csv 正常结束"
    if result.status == "stalled":
        step = result.step
        return False, f"recovery.csv 卡死: {step.flow_name}:{step.index}:{step.operate}"
    return False, "recovery.csv 被停止"


def run_config_with_recovery(
    config_dir: str,
    real_input: BaseInput,
    scale_helper: ScaleHelper,
    loop: bool,
    print_log: bool,
    stop_event: Event,
) -> None:
    resolver = RuntimeConfigResolver(config_dir)
    watchdog_settings = resolver.get_watchdog_settings()
    recovery_count = 0
    session, watchdog = create_main_session(
        config_dir,
        real_input,
        scale_helper,
        loop,
        print_log,
        watchdog_settings,
        recovery_count,
    )

    while not stop_event.is_set():
        result = _run_session_until_boundary(session, watchdog, stop_event)
        if result.status == "finished":
            return
        if result.status == "stopped":
            return
        if result.status != "stalled":
            raise RuntimeError(f"未知运行结果: {result.status}")

        step = result.step
        elapsed = watchdog._time_fn() - watchdog.last_progress_at
        log.warning(
            f"检测到流程卡死，准备执行 recovery.csv。当前位置: {step.flow_name}:{step.index}:{step.operate}，"
            f"距离上次有效操作 {elapsed:.2f}s，累计非有效操作 {watchdog.non_progress_count_since_progress}"
        )

        if watchdog_settings.recovery_limit >= 0 and recovery_count >= watchdog_settings.recovery_limit:
            log.error(f"recovery 次数已达上限 {watchdog_settings.recovery_limit}，终止当前实例")
            return

        recovery_count += 1
        screenshot_path = capture_recovery_screenshot(config_dir, step)
        if screenshot_path is not None:
            log.warning(f"已保存 recovery 全屏截图: {screenshot_path}")
        success, reason = run_recovery_flow(
            config_dir=config_dir,
            real_input=real_input,
            scale_helper=scale_helper,
            print_log=print_log,
            runtime_resolver=resolver,
            stop_event=stop_event,
            recovery_count=recovery_count,
        )
        if not success:
            log.error(f"恢复失败，终止当前实例: {reason}")
            return

        log.warning(f"恢复成功，第 {recovery_count} 次 recovery 完成，重新从 main.csv 开始: {reason}")
        session, watchdog = create_main_session(
            config_dir,
            real_input,
            scale_helper,
            loop,
            print_log,
            watchdog_settings,
            recovery_count,
        )


def has_recovery_flow(config_dir: str) -> bool:
    return (Path(config_dir) / "recovery.csv").exists()
