import time


class ExecutionWatchdog:
    def __init__(self, stall_timeout_seconds: float, stall_non_progress_ops: int, time_fn=None):
        self.stall_timeout_seconds = float(stall_timeout_seconds)
        self.stall_non_progress_ops = int(stall_non_progress_ops)
        self._time_fn = time_fn or time.monotonic
        now = self._time_fn()
        self.last_progress_at = now
        self.non_progress_count_since_progress = 0
        self.current_step_had_progress = False

    def begin_step(self):
        self.current_step_had_progress = False

    def record_progress(self, detail: str, source: str = "input"):
        now = self._time_fn()
        self.last_progress_at = now
        self.non_progress_count_since_progress = 0
        self.current_step_had_progress = True

    def record_observation(self, detail: str, source: str = "node"):
        self.non_progress_count_since_progress += 1

    def should_recover(self, now: float | None = None) -> bool:
        current_time = self._time_fn() if now is None else now
        elapsed = current_time - self.last_progress_at
        return (
            elapsed >= self.stall_timeout_seconds
            and self.non_progress_count_since_progress >= self.stall_non_progress_ops
        )
