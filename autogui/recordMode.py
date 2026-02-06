import os
import time
import datetime
import csv
import winsound
import keyboard
import mouse
import threading
from . import log


recordDir = 'record'


class RecordMode:
    """记录鼠标和键盘事件，并将其导出为与 main.csv 相同格式的 CSV 文件。

    - 按下 shift+x 开始记录，再按一次停止并保存文件。
    - 记录的每一行会包含：序号、操作、操作参数、完成后等待时间（与上一事件的时间差）等字段。
    """

    def __init__(self):
        if not os.path.exists(recordDir):
            os.makedirs(recordDir)
        self._recording = False
        self._events = []
        self._last_time = None
        self._kbd_hook = None
        self._mouse_hook = None
        self._last_move_time = 0
        self._move_min_interval = 1  # 秒，限制移动事件频率，避免爆炸性记录
        # 跟踪当前按下但尚未释放的按键，避免键盘自动重复触发导致多次记录
        self._pressed_keys = set()

        # 捕获当前线程日志绑定（实例线程），用于在回调线程恢复
        self._log_binding = log.capture_binding()
        keyboard.add_hotkey('shift+x', log.wrap_callback(self.ToggleRecord, self._log_binding))
        log.info('按下 shift + x 开始/停止录制（录制时会捕获鼠标与键盘事件）')

    def ToggleRecord(self):
        if not self._recording:
            self.StartRecord()
        else:
            self.StopRecord()

    def StartRecord(self):
        log.info('开始录制...')
        self._events = []
        self._last_time = time.time()
        threading.Thread(target=lambda: winsound.MessageBeep(winsound.MB_ICONHAND), daemon=True).start()
        # 注册钩子
        try:
            self._kbd_hook = keyboard.hook(log.wrap_callback(self._on_keyboard_event, self._log_binding))
        except Exception as e:
            log.error('无法挂载 keyboard 钩子:', e)
            self._kbd_hook = None

        try:
            self._mouse_hook = mouse.hook(log.wrap_callback(self._on_mouse_event, self._log_binding))
        except Exception as e:
            log.error('无法挂载 mouse 钩子:', e)
            self._mouse_hook = None

        self._recording = True

    def StopRecord(self):
        log.info('停止录制，准备保存...')
        threading.Thread(target=lambda: winsound.MessageBeep(winsound.MB_ICONHAND), daemon=True).start()
        # 取消钩子
        try:
            if self._kbd_hook is not None:
                keyboard.unhook(self._kbd_hook)
        except Exception:
            pass
        try:
            if self._mouse_hook is not None:
                mouse.unhook(self._mouse_hook)
        except Exception:
            pass

        self._recording = False
        self.SaveCsv()

    def _on_keyboard_event(self, event):
        # event.event_type: 'down' or 'up'
        # event.name: key name
        now = time.time()
        # 记录时间戳，保存时再计算每条事件之后的等待时间
        self._last_time = now

        # try:
        #     print(f"Keyboard event: {event.event_type} key: {event.name}")
        # except Exception:
        #     pass

        try:
            etype = event.event_type
            name = event.name
        except Exception:
            return

        # 标准化名称为字符串
        key_name = str(name) if name is not None else ''

        if etype == 'down':
            # 如果该键已记录为按下（尚未收到 kUp），则忽略后续的重复 down 事件
            if key_name in self._pressed_keys:
                return
            self._pressed_keys.add(key_name)
            self._events.append({'op': 'kDown', 'param': key_name, 'time': now})
            return

        if etype == 'up':
            # 记录按键释放，并从按下集合中移除（若存在）
            self._events.append({'op': 'kUp', 'param': key_name, 'time': now})
            try:
                if key_name in self._pressed_keys:
                    self._pressed_keys.remove(key_name)
            except Exception:
                pass
            return

    def _on_mouse_event(self, event):
        # event.event_type could be 'move','wheel','down','up' depending on mouse lib
        now = time.time()
        # 记录时间戳，保存时再计算每条事件之后的等待时间
        self._last_time = now

        # 不同 mouse 版本/平台返回的事件对象略有不同，做更稳健的检测
        etype = getattr(event, 'event_type', None)
        x = getattr(event, 'x', None)
        y = getattr(event, 'y', None)
        # 有些实现使用 'button'，有些使用 'button_name' 或 'button_code'
        button = None
        if hasattr(event, 'button'):
            button = getattr(event, 'button')
        elif hasattr(event, 'button_name'):
            button = getattr(event, 'button_name')
        elif hasattr(event, 'button_code'):
            button = getattr(event, 'button_code')

        # 如果 event_type 为空但有坐标，视为移动事件
        if etype is None and x is not None and y is not None:
            etype = 'move'

        # try:
        #     print(f"Mouse event: {etype} at ({x},{y}) button: {button}")
        # except Exception:
        #     pass

        # 鼠标按下/释放
        if etype in ('down',) and button is not None:
            self._events.append({'op': 'mDown', 'param': str(button), 'time': now})
            return
        if etype in ('up',) and button is not None:
            self._events.append({'op': 'mUp', 'param': str(button), 'time': now})
            return

        # 鼠标移动事件（有坐标）
        # if etype in ('move',):
        #     # 限制频率
        #     if now - self._last_move_time < self._move_min_interval:
        #         return
        #     self._last_move_time = now
        #     try:
        #         px = int(x)
        #         py = int(y)
        #     except Exception:
        #         # 如果坐标不可用，则跳过
        #         return
        #     self._events.append({'op': 'mMoveTo', 'param': f"{px};{py}", 'time': now})
        #     return

    def SaveCsv(self):
        if len(self._events) == 0:
            log.info('未捕获到事件，未生成文件。')
            return

        time_str = datetime.datetime.now().strftime("%m%d%H%M%S")
        filename = f"record_{time_str}.csv"
        filepath = os.path.join(recordDir, filename)

        # 写 CSV，保持与 main.csv 相同的列顺序
        headers = ['序号','操作','操作参数','完成后等待时间','图片/ocr名称','图片/ocr坐标范围','图片/ocr置信度','未找到图片/ocr重试时间','图片/ocr定位移动随机','移动操作用时']

        try:
            with open(filepath, mode='w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
                idx = 1
                for i, ev in enumerate(self._events):
                    row = [''] * len(headers)
                    row[0] = idx
                    row[1] = ev.get('op','')
                    row[2] = ev.get('param','')
                    # 计算完成后等待时间：到下一事件的时间差（秒）
                    wait_time = ''
                    if 'time' in ev:
                        if i < len(self._events) - 1 and 'time' in self._events[i+1]:
                            try:
                                wait_time = round(self._events[i+1]['time'] - ev['time'], 3)
                            except Exception:
                                wait_time = ''
                        else:
                            # 最后一条事件，设为 0
                            wait_time = 0
                    row[3] = wait_time
                    writer.writerow(row)
                    idx += 1
            log.info(f'录制文件已保存: {filepath}')
        except Exception as e:
            log.error('保存 CSV 出错:', e)

    def Update(self):
        # 供主循环调用，简单 sleep 即可
        time.sleep(1)
        return True
