from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..runtime.context import RuntimeContext
from .operator import AutoOperator


class SessionStatus(StrEnum):
    FINISHED = "finished"
    STOPPED = "stopped"
    STALLED = "stalled"


@dataclass(frozen=True)
class StepInfo:
    flow_name: str
    index: int
    operate: str


@dataclass(frozen=True)
class SessionRunResult:
    status: SessionStatus
    step: StepInfo | None = None


class FlowRuntimeSession:
    def __init__(
        self,
        runtime_context: RuntimeContext,
        source_file: str = "main.csv",
        loop: bool = False,
    ) -> None:
        self.runtime_context = runtime_context
        self.sub_operator_list: list[AutoOperator] = []
        self.main_operator = AutoOperator(
            runtime_context.get_compiled_flow(source_file),
            runtime_context,
            self.sub_operator_list,
            loop,
        )
        self.main_finished = False

    def get_active_operator(self) -> AutoOperator | None:
        while self.sub_operator_list:
            operator = self.sub_operator_list[-1]
            if operator.has_current_operation:
                return operator
            self.sub_operator_list.pop()

        if self.main_finished or not self.main_operator.has_current_operation:
            self.main_finished = True
            return None
        return self.main_operator

    def peek_current_step(self) -> StepInfo | None:
        operator = self.get_active_operator()
        if operator is None:
            return None
        operation = operator.peek_current_operation()
        return StepInfo(operator.source_file, operation.index, operation.operation)

    def step(self) -> bool:
        operator = self.get_active_operator()
        if operator is None:
            return False

        if operator is not self.main_operator:
            if not operator.Update():
                if self.sub_operator_list and self.sub_operator_list[-1] is operator:
                    self.sub_operator_list.pop()
            return True

        if not self.main_operator.Update():
            self.main_finished = True
            return False
        return True


def run_session_without_watchdog(
    runtime_context: RuntimeContext,
    source_file: str = "main.csv",
    loop: bool = False,
) -> SessionRunResult:
    session = FlowRuntimeSession(
        runtime_context,
        source_file=source_file,
        loop=loop,
    )
    last_step: StepInfo | None = None
    stop_event = runtime_context.stop_event
    if stop_event is None:
        raise RuntimeError("RuntimeContext.stop_event 未初始化")
    while not stop_event.is_set():
        step = session.peek_current_step()
        if step is None:
            return SessionRunResult(SessionStatus.FINISHED, last_step)
        last_step = step
        has_more = session.step()
        if not has_more and not session.sub_operator_list:
            return SessionRunResult(SessionStatus.FINISHED, step)
    return SessionRunResult(SessionStatus.STOPPED, last_step)
