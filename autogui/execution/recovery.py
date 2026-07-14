import datetime
import traceback
import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
import re
from threading import Event

import pyautogui
import win32con

from ..infrastructure import log
from ..input.base import BaseInput
from ..input.observed import ObservedInput
from ..notifications.runtime import NotificationRequest, dispatch_notification
from ..runtime.config import RuntimeConfigResolver, WatchdogSettings, WatchdogThresholds
from ..runtime.context import RuntimeContext
from .session import (
    FlowRuntimeSession,
    SessionRunResult,
    SessionStatus,
    StepInfo,
)
from .watchdog import ExecutionWatchdog


NON_PROGRESS_OPERATIONS = {"mMove", "mMoveTo", "pic", "ocr", "jmp", "notify", "script"}
STALL_SCREENSHOT_DIR = Path("screenshot")
_FILENAME_SANITIZE_PATTERN = re.compile(r'[<>:"/\\|?*\s]+')


@dataclass(frozen=True)
class RecoveryRunResult:
    resolution: str
    detail: str
    unresolved_reason: str | None = None


def _run_session_until_boundary(
    session: FlowRuntimeSession,
    watchdog: ExecutionWatchdog,
    stop_event: Event,
) -> SessionRunResult:
    while not stop_event.is_set():
        step = session.peek_current_step()
        if step is None:
            return SessionRunResult(SessionStatus.FINISHED)

        watchdog.begin_step()
        has_more = session.step()
        if not watchdog.current_step_had_progress and step.operate in NON_PROGRESS_OPERATIONS:
            watchdog.record_observation(step.operate, source="node")

        if watchdog.should_recover():
            return SessionRunResult(
                SessionStatus.STALLED,
                step,
            )

        if not has_more and not session.sub_operator_list:
            return SessionRunResult(SessionStatus.FINISHED, step)

    return SessionRunResult(SessionStatus.STOPPED)


def _sanitize_filename_part(value: str) -> str:
    sanitized = _FILENAME_SANITIZE_PATTERN.sub("_", value.strip())
    sanitized = sanitized.strip("._")
    return sanitized or "unknown"


def capture_stall_screenshot(config_dir: str, step: StepInfo | None) -> Path | None:
    try:
        left = ctypes.windll.user32.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        top = ctypes.windll.user32.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        width = ctypes.windll.user32.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
        height = ctypes.windll.user32.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
        screenshot = pyautogui.screenshot(region=(left, top, width, height))
        STALL_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        config_name = _sanitize_filename_part(Path(config_dir).name)
        flow_name = _sanitize_filename_part(step.flow_name if step is not None else "unknown_flow")
        index = "unknown" if step is None else str(step.index)
        output_path = STALL_SCREENSHOT_DIR / f"stall_{config_name}_{flow_name}_{index}_{timestamp}.png"
        screenshot.save(output_path)
        return output_path
    except Exception:
        log.error(f"保存 stall 全屏截图失败\n{traceback.format_exc()}")
        return None


def create_main_session(
    runtime_context: RuntimeContext,
    real_input: BaseInput,
    loop: bool,
    watchdog_settings: WatchdogSettings,
) -> tuple[FlowRuntimeSession, ExecutionWatchdog]:
    watchdog = ExecutionWatchdog(
        watchdog_settings.stall_timeout_seconds,
        watchdog_settings.stall_non_progress_ops,
    )
    observed_input = ObservedInput(real_input, watchdog)
    runtime_context.set_input(observed_input)
    session = FlowRuntimeSession(
        runtime_context,
        source_file="main.csv",
        loop=loop,
    )
    return session, watchdog


def run_recovery_flow(
    runtime_context: RuntimeContext,
    real_input: BaseInput,
    runtime_resolver: RuntimeConfigResolver,
) -> RecoveryRunResult:
    stop_event = runtime_context.stop_event
    if stop_event is None:
        raise RuntimeError("RuntimeContext.stop_event 未初始化")
    thresholds: WatchdogThresholds = runtime_resolver.get_recovery_watchdog_thresholds()
    watchdog = ExecutionWatchdog(
        thresholds.stall_timeout_seconds,
        thresholds.stall_non_progress_ops,
    )
    observed_input = ObservedInput(real_input, watchdog)
    previous_input = runtime_context.input
    previous_state = runtime_context.state
    runtime_context.state = {}
    runtime_context.set_input(observed_input)
    try:
        session = FlowRuntimeSession(
            runtime_context,
            source_file="recovery.csv",
            loop=False,
        )
        result = _run_session_until_boundary(session, watchdog, stop_event)
    except Exception:
        log.error(f"执行 recovery.csv 失败\n{traceback.format_exc()}")
        return RecoveryRunResult(
            resolution="failed",
            detail="recovery.csv 抛出异常",
            unresolved_reason="recovery_failed",
        )
    finally:
        runtime_context.state = previous_state
        runtime_context.set_input(previous_input)
    if result.status == SessionStatus.FINISHED:
        return RecoveryRunResult("success", "recovery.csv 正常结束")
    if result.status == SessionStatus.STALLED:
        step = result.step
        return RecoveryRunResult(
            resolution="failed",
            detail=f"recovery.csv 卡死: {step.flow_name}:{step.index}:{step.operate}",
            unresolved_reason="recovery_stalled",
        )
    return RecoveryRunResult("stopped", "recovery.csv 被停止")


def _build_unresolved_notification_request(
    config_dir: str,
    step: StepInfo | None,
    unresolved_reason: str,
    detail: str,
    screenshot_path: Path | None,
    runtime_resolver: RuntimeConfigResolver,
) -> NotificationRequest:
    policy = runtime_resolver.get_unresolved_stall_policy()
    config_name = Path(config_dir).name
    metadata = {
        "config": config_name,
        "reason": unresolved_reason,
    }
    lines = [f"流程卡死后未能自动恢复。原因: {unresolved_reason}", detail]
    if step is not None:
        metadata["flow"] = step.flow_name
        metadata["index"] = step.index
        metadata["operate"] = step.operate
        lines.append(f"位置: {step.flow_name}:{step.index}:{step.operate}")
    if screenshot_path is not None:
        metadata["screenshot"] = screenshot_path

    return NotificationRequest(
        source="stall_unresolved",
        title=f"CsvAutoGui 流程卡死: {config_name}",
        message="\n".join(lines),
        local_notify=policy.local_notify,
        remote_notify=policy.remote_notify,
        screenshot_path=None if screenshot_path is None else str(screenshot_path),
        metadata=metadata,
    )


def _handle_unresolved_stall(
    config_dir: str,
    step: StepInfo | None,
    unresolved_reason: str,
    detail: str,
    screenshot_path: Path | None,
    runtime_resolver: RuntimeConfigResolver,
) -> None:
    request = _build_unresolved_notification_request(
        config_dir=config_dir,
        step=step,
        unresolved_reason=unresolved_reason,
        detail=detail,
        screenshot_path=screenshot_path,
        runtime_resolver=runtime_resolver,
    )
    log.error(f"流程卡死未解决，终止当前实例: {detail}")
    dispatch_notification(request)


def run_config_with_watchdog(
    runtime_context: RuntimeContext,
    real_input: BaseInput,
    loop: bool,
    runtime_resolver: RuntimeConfigResolver,
) -> None:
    config_dir = os.fspath(runtime_context.config_dir)
    stop_event = runtime_context.stop_event
    if stop_event is None:
        raise RuntimeError("RuntimeContext.stop_event 未初始化")
    resolver = runtime_resolver
    watchdog_settings = resolver.get_watchdog_settings()
    recovery_count = 0
    session, watchdog = create_main_session(
        runtime_context,
        real_input,
        loop,
        watchdog_settings,
    )

    while not stop_event.is_set():
        result = _run_session_until_boundary(session, watchdog, stop_event)
        if result.status == SessionStatus.FINISHED:
            return
        if result.status == SessionStatus.STOPPED:
            return
        if result.status != SessionStatus.STALLED:
            raise RuntimeError(f"未知运行结果: {result.status}")

        step = result.step
        elapsed = watchdog._time_fn() - watchdog.last_progress_at
        log.warning(
            f"检测到流程卡死，进入 stall 处理链。当前位置: {step.flow_name}:{step.index}:{step.operate}，"
            f"距离上次有效操作 {elapsed:.2f}s，累计非有效操作 {watchdog.non_progress_count_since_progress}"
        )

        screenshot_path = capture_stall_screenshot(config_dir, step)
        if screenshot_path is not None:
            log.warning(f"已保存 stall 全屏截图: {screenshot_path}")

        if not resolver.recovery_enabled:
            _handle_unresolved_stall(
                config_dir=config_dir,
                step=step,
                unresolved_reason="no_recovery",
                detail="当前配置未提供 recovery.csv",
                screenshot_path=screenshot_path,
                runtime_resolver=resolver,
            )
            return

        if watchdog_settings.recovery_limit >= 0 and recovery_count >= watchdog_settings.recovery_limit:
            _handle_unresolved_stall(
                config_dir=config_dir,
                step=step,
                unresolved_reason="recovery_limit_reached",
                detail=f"recovery 次数已达上限 {watchdog_settings.recovery_limit}",
                screenshot_path=screenshot_path,
                runtime_resolver=resolver,
            )
            return

        recovery_count += 1
        recovery_result = run_recovery_flow(
            runtime_context=runtime_context,
            real_input=real_input,
            runtime_resolver=resolver,
        )
        if recovery_result.resolution == "stopped":
            return
        if recovery_result.resolution != "success":
            _handle_unresolved_stall(
                config_dir=config_dir,
                step=step,
                unresolved_reason=recovery_result.unresolved_reason or "recovery_failed",
                detail=recovery_result.detail,
                screenshot_path=screenshot_path,
                runtime_resolver=resolver,
            )
            return

        log.warning(f"恢复成功，第 {recovery_count} 次 recovery 完成，重新从 main.csv 开始: {recovery_result.detail}")
        runtime_context.reset_business_state()
        session, watchdog = create_main_session(
            runtime_context,
            real_input,
            loop,
            watchdog_settings,
        )
