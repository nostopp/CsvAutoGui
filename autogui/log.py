"""
轻量日志模块，用于在命令行（默认 print）和 GUI（回调）之间切换。

用法：
  from autogui import log
  log.info('message')

API:
  set_handler(fn)            # 将日志处理切换到 fn(msg:str)
  reset_handler()            # 恢复默认 print 行为
  set_context(dict)          # 为当前线程设置上下文（例如 {'name': 'config1'}）
  clear_context()            # 清除当前线程上下文
  info/debug/warning/error   # 日志方法

注意：上下文是线程局部的，适用于 GUI 中多个实例并发运行时区分来源。
"""
import threading
import traceback

_thread_local = threading.local()
_handler = None


# 线程级 handler 支持（避免多线程时相互覆盖）
def set_thread_handler(fn):
    """为当前线程设置 handler(fn: str)"""
    _thread_local.handler = fn

def get_thread_handler():
    """获取当前线程的 handler(fn: str)"""
    return getattr(_thread_local, 'handler', None)


def reset_thread_handler():
    if hasattr(_thread_local, 'handler'):
        del _thread_local.handler


def set_handler(fn):
    """设置全局日志处理函数，fn(msg: str)"""
    global _handler
    _handler = fn


def reset_handler():
    """恢复默认处理（print）"""
    global _handler
    _handler = None


def set_thread_context(ctx: dict):
    """为当前线程设置上下文（字典）"""
    _thread_local.context = ctx


def clear_thread_context():
    if hasattr(_thread_local, 'context'):
        del _thread_local.context


def get_thread_context():
    return getattr(_thread_local, 'context', None)


def _emit(level: str, msg: str):
    try:
        ctx = get_thread_context()
        prefix = ''
        if isinstance(ctx, dict):
            name = ctx.get('name') or ctx.get('id')
            if name:
                prefix = f"[{name}] "

        text = f"{prefix}[{level}] {msg}"
        # 优先使用线程级 handler，然后是全局 handler，最后回退到 print
        handler = getattr(_thread_local, 'handler', None) or _handler
        if handler:
            try:
                handler(text)
            except Exception:
                # 保底：handler 出错时仍然打印
                print(text, flush=True)
                traceback.print_exc()
        else:
            print(text, flush=True)
    except Exception:
        # 日志模块不应该抛出
        try:
            print(f"[LOG_ERROR] {msg}", flush=True)
        except Exception:
            pass


def capture_binding():
    """
    捕获当前线程的日志绑定（线程级 handler 与上下文），用于跨线程回放。
    返回 dict: { 'handler': handler or None, 'context': context or None }
    """
    h = get_thread_handler()
    c = get_thread_context()
    return {'handler': h, 'context': c}


def wrap_callback(fn, binding: dict):
    """
    包装一个回调，使其执行期间设置指定的线程级 handler 与上下文，执行后恢复原先状态。
    可用于 keyboard/mouse 等库在其他线程触发的回调。
    """
    def _wrapped(*args, **kwargs):
        prev_h = get_thread_handler()
        prev_c = get_thread_context()
        try:
            if binding is not None:
                bh = binding.get('handler', None)
                bc = binding.get('context', None)
                if bh is not None:
                    set_thread_handler(bh)
                if bc is not None:
                    set_thread_context(bc)
            return fn(*args, **kwargs)
        finally:
            # 恢复之前的 handler/context
            try:
                if prev_h is not None:
                    set_thread_handler(prev_h)
                else:
                    reset_thread_handler()
            except Exception:
                pass
            try:
                if prev_c is not None:
                    set_thread_context(prev_c)
                else:
                    clear_thread_context()
            except Exception:
                pass
    return _wrapped


def info(msg: str):
    _emit('INFO', msg)


def debug(msg: str):
    _emit('DEBUG', msg)


def warning(msg: str):
    _emit('WARN', msg)


def error(msg: str):
    _emit('ERROR', msg)
