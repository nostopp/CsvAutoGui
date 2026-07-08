from dataclasses import dataclass, field
from pathlib import Path
import threading
from typing import Any

from serverchan_sdk import sc_send

from . import log
from . import notifier
from .runtime_config import NotificationRouteSettings, NotificationSettings


_thread_local = threading.local()
DEFAULT_NOTIFY_ROUTES = NotificationRouteSettings(local_notify=True, remote_notify=False)


@dataclass(frozen=True)
class NotificationRequest:
    source: str
    title: str
    message: str
    local_notify: bool
    remote_notify: bool
    screenshot_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NotificationDispatchResult:
    local_attempted: bool
    local_sent: bool
    remote_attempted: bool
    remote_sent: bool


def configure_thread_notifications(settings: NotificationSettings) -> None:
    _thread_local.settings = settings


def clear_thread_notifications() -> None:
    if hasattr(_thread_local, "settings"):
        del _thread_local.settings


def get_thread_notification_settings() -> NotificationSettings | None:
    return getattr(_thread_local, "settings", None)


def notify_operation(text: str | None = None) -> NotificationDispatchResult:
    message = _normalize_message(text)
    settings = get_thread_notification_settings()
    routes = DEFAULT_NOTIFY_ROUTES if settings is None else settings.notify_operation
    return dispatch_notification(
        NotificationRequest(
            source="notify_operation",
            title="CsvAutoGui Notify",
            message=message,
            local_notify=routes.local_notify,
            remote_notify=routes.remote_notify,
        )
    )


def dispatch_notification(request: NotificationRequest) -> NotificationDispatchResult:
    local_attempted = False
    local_sent = False
    remote_attempted = False
    remote_sent = False

    if request.local_notify:
        local_attempted = True
        try:
            notifier.notify(_build_local_message(request), beep=True)
            local_sent = True
        except Exception as exc:
            log.error(f"本地通知发送失败: {exc}")

    if request.remote_notify:
        remote_attempted = True
        try:
            remote_sent = _send_remote_notification(request)
        except Exception as exc:
            log.error(f"远程通知发送失败: {exc}")

    return NotificationDispatchResult(
        local_attempted=local_attempted,
        local_sent=local_sent,
        remote_attempted=remote_attempted,
        remote_sent=remote_sent,
    )


def _send_remote_notification(request: NotificationRequest) -> bool:
    settings = get_thread_notification_settings()
    if settings is None:
        log.warning("当前线程未配置通知设置，跳过远程通知")
        return False

    remote_settings = settings.remote
    if not remote_settings.enabled:
        log.warning("远程通知未启用，跳过发送")
        return False
    if not remote_settings.sendkey:
        log.warning("远程通知缺少 sendkey，跳过发送")
        return False

    response = sc_send(
        remote_settings.sendkey,
        request.title,
        _build_remote_body(request),
    )
    code = response.get("code") if isinstance(response, dict) else None
    if code not in (None, 0):
        log.warning(f"远程通知返回非成功结果: {response}")
        return False

    log.info(f"远程通知已发送: {request.title}")
    return True


def _normalize_message(text: str | None) -> str:
    if text is None:
        return "notify"
    message = str(text).strip()
    return message or "notify"


def _build_local_message(request: NotificationRequest) -> str:
    if request.source == "notify_operation":
        return request.message

    lines = [request.title, request.message]
    if request.screenshot_path:
        lines.append(f"截图: {request.screenshot_path}")
    return "\n".join(line for line in lines if line)


def _build_remote_body(request: NotificationRequest) -> str:
    lines = [request.message]
    if request.screenshot_path:
        lines.append(f"截图: `{Path(request.screenshot_path)}`")

    if request.metadata:
        lines.append("")
        lines.append("上下文:")
        for key, value in request.metadata.items():
            lines.append(f"- {key}: `{value}`")

    return "\n".join(lines)
