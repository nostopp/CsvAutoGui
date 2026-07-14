# 当前模式示例

这里只提供最小结构，用于确认当前语义。完整 CSV 必须使用 `csv_schema.py` 的全部中文列，完整示例以 `config/example/` 为准。

## 子流程分支

识别节点的 `操作参数`：

```text
exist;input_actions.csv
notExist;fallback.csv
```

条件满足时启动对应子流程；子流程结束后，从当前流程的下一行继续。

## 双跳转分支

```text
exist;matched;unmatched
notExist;missing;present
```

第二、第三段都必须是当前流程中存在的序号、跳转标记或负整数。不要把文件名放进三段式双跳转。

若某一分支需要立即结束当前流程，可将该落点写为负整数（推荐 `-1`）：

```text
notExist;-1;retry
```

终止分支不会执行后续节点或等待时间；若位于子流程，它会返回父流程。

## 脚本与运行时资源

推荐入口：

```python
from autogui.scripting.runtime import ScriptBase


class ExampleScript(ScriptBase):
    def run(self):
        match = self.ctx.find_image(resource="entry_button")
        if match is None:
            return self.next_step()
        self.ctx.state["entry_seen"] = True
        return self.start_subflow("enter.csv")


def run(ctx):
    return ExampleScript(ctx).run()
```

对应资源文件行的关键字段：

```text
操作=resource
操作参数=pic;entry_button
图片/ocr名称=entry_button.png
图片/ocr坐标范围=100;200;300;120
```

脚本节点使用 `example.py` 时，默认尝试 `example_resource.csv`；使用 `example.py;shared_resource.csv` 时显式加载指定资源。

`ctx.find_image`、`ctx.find_text` 和 `ctx.sleep` 只属于观察。需要刷新 watchdog 进展时，必须发生真实的 `ctx.input` 输入操作。

## watchdog 与 recovery

```json
{
  "watchdog": {
    "mode": "auto",
    "stall_timeout_seconds": 90,
    "stall_non_progress_ops": 60,
    "recovery_limit": 2,
    "recovery_watchdog": {
      "stall_timeout_seconds": 30,
      "stall_non_progress_ops": 20
    }
  }
}
```

`recovery_watchdog` 只能位于 `watchdog` 内。recovery 不依赖主流程业务 state；恢复成功后框架丢弃原业务 state，并从 `main.csv` 重启。

## stall 与 notify 通知

```json
{
  "on_stall_unresolved": {
    "local_notify": true,
    "remote_notify": true
  },
  "notification": {
    "notify_operation": {
      "local_notify": true,
      "remote_notify": false
    },
    "remote": {
      "enabled": true,
      "sendkey_env": "CSV_AUTOGUI_SERVERCHAN_SENDKEY"
    }
  }
}
```

`on_stall_unresolved` 控制自动恢复无法闭环后的终态通知；`notification.notify_operation` 控制普通 `notify` 节点。两者不能混为同一策略。

## 阶段性资源清单

阶段 2、3 的 `<config_name>_resource.csv` 只允许：

```text
操作=resource, 操作参数=pic;alias
操作=resource, 操作参数=ocr;alias
```

编写清单不能包含 `操作参数=jmp;alias`。最终要么被脚本正式引用，要么在获得用户同意后清理。
