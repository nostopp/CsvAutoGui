import threading
import argparse
import tkinter as tk
from tkinter import scrolledtext, messagebox
import main as main_module


class InstanceEntry:
    def __init__(self, iid, name, args):
        self.id = iid
        self.name = name
        self.args = args
        self.thread = None
        self.stop_event = threading.Event()
        self.logs = []
        self.running = False


class MainWindow:
    def __init__(self, root):
        self.root = root
        root.title('CsvAutoGui Manager')

        # 默认参数来源于 main.parse_args 的默认值
        defaults = main_module.parse_args([])

        frm_top = tk.Frame(root)
        frm_top.pack(fill=tk.X, padx=6, pady=6)

        tk.Label(frm_top, text='config').grid(row=0, column=0, sticky='w')
        self.e_config = tk.Entry(frm_top, width=40)
        self.e_config.insert(0, defaults.config)
        self.e_config.grid(row=0, column=1, columnspan=3, sticky='w')

        self.var_loop = tk.BooleanVar(value=defaults.loop)
        tk.Checkbutton(frm_top, text='loop', variable=self.var_loop).grid(row=1, column=0)

        self.var_log = tk.BooleanVar(value=defaults.log)
        tk.Checkbutton(frm_top, text='log', variable=self.var_log).grid(row=1, column=1)

        tk.Label(frm_top, text='scale').grid(row=2, column=0)
        self.e_scale = tk.Entry(frm_top, width=4)
        self.e_scale.insert(0, str(defaults.scale))
        self.e_scale.grid(row=2, column=1)

        tk.Label(frm_top, text='offset').grid(row=2, column=2)
        self.e_offset = tk.Entry(frm_top, width=4)
        self.e_offset.insert(0, defaults.offset)
        self.e_offset.grid(row=2, column=3)

        self.var_scale_image = tk.BooleanVar(value=defaults.scale_image)
        tk.Checkbutton(frm_top, text='scale_image', variable=self.var_scale_image).grid(row=2, column=4)

        tk.Label(frm_top, text='title').grid(row=3, column=0)
        self.e_title = tk.Entry(frm_top, width=40)
        if defaults.title:
            self.e_title.insert(0, defaults.title)
        self.e_title.grid(row=3, column=1)

        self.var_multi = tk.BooleanVar(value=defaults.multi_window)
        tk.Checkbutton(frm_top, text='multi_window', variable=self.var_multi).grid(row=3, column=2)

        self.var_process = tk.BooleanVar(value=defaults.process)
        tk.Checkbutton(frm_top, text='process', variable=self.var_process).grid(row=4, column=0)

        self.var_screenshots = tk.BooleanVar(value=defaults.screenshots)
        tk.Checkbutton(frm_top, text='screenshots', variable=self.var_screenshots).grid(row=4, column=1)

        self.var_record = tk.BooleanVar(value=defaults.record)
        tk.Checkbutton(frm_top, text='record', variable=self.var_record).grid(row=4, column=2)

        btn_start = tk.Button(frm_top, text='Start Instance', command=self.start_instance)
        btn_start.grid(row=5, column=0, pady=6)

        btn_stop = tk.Button(frm_top, text='Stop Selected', command=self.stop_selected)
        btn_stop.grid(row=5, column=1)

        btn_stop_all = tk.Button(frm_top, text='Stop All', command=self.stop_all)
        btn_stop_all.grid(row=5, column=2)

        btn_restart = tk.Button(frm_top, text='Restart Selected', command=self.restart_selected)
        btn_restart.grid(row=5, column=3)

        # 中部：实例列表 + 日志显示
        frm_mid = tk.Frame(root)
        frm_mid.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.listbox = tk.Listbox(frm_mid, width=36)
        self.listbox.pack(side=tk.LEFT, fill=tk.Y)
        self.listbox.bind('<<ListboxSelect>>', self.on_select)

        self.txt_log = scrolledtext.ScrolledText(frm_mid, state='disabled')
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frm_bottom = tk.Frame(root)
        frm_bottom.pack(fill=tk.X, padx=6, pady=6)

        btn_clear = tk.Button(frm_bottom, text='Clear Logs', command=self.clear_logs)
        btn_clear.pack(side=tk.LEFT)

        # 快捷键说明
        lbl_hotkey = tk.Label(frm_bottom, text='快捷键 Shift+Ctrl+X：停止所有实例', fg='blue')
        lbl_hotkey.pack(side=tk.LEFT, padx=12)

        # 绑定全局快捷键
        self.root.bind_all('<Control-Shift-x>', lambda e: self.stop_all())
        self.root.bind_all('<Control-Shift-X>', lambda e: self.stop_all())

        self.instances = {}
        self.next_id = 1

    def build_args(self):
        # 构造 argparse.Namespace 兼容对象
        try:
            scale = float(self.e_scale.get())
        except Exception:
            scale = 1.0

        ns = argparse.Namespace(
            config=self.e_config.get(),
            loop=self.var_loop.get(),
            log=self.var_log.get(),
            screenshots=self.var_screenshots.get(),
            scale=scale,
            scale_image=self.var_scale_image.get(),
            offset=self.e_offset.get(),
            title=self.e_title.get() or None,
            multi_window=self.var_multi.get(),
            process=self.var_process.get(),
            record=self.var_record.get(),
            _from_window=True,
        )
        return ns

    def _launch_instance_thread(self, inst):
        """内部方法：为 InstanceEntry 创建并启动后台线程"""
        def log_cb(msg: str):
            if not msg.endswith('\n'):
                msg = msg + '\n'
            inst.logs.append(msg)
            if len(inst.logs) > 5000:
                inst.logs = inst.logs[-2500:]

            def _update():
                sel = self.get_selected_instance()
                if sel and sel.id == inst.id:
                    self.txt_log['state'] = 'normal'
                    self.txt_log.insert(tk.END, msg)
                    self.txt_log.see(tk.END)
                    self.txt_log['state'] = 'disabled'

            self.root.after(1, _update)

        def target():
            inst.running = True
            def _mark_running():
                try:
                    keys = list(self.instances.keys())
                    idx = keys.index(inst.id)
                    self.listbox.delete(idx)
                    self.listbox.insert(idx, f"{inst.name} (id:{inst.id}) [running]")
                except Exception:
                    pass

            try:
                self.root.after(1, _mark_running)
            except Exception:
                pass

            try:
                main_module.start_instance(inst.args, log_callback=log_cb, stop_event=inst.stop_event, use_hotkey=False)
            except Exception as e:
                log_cb(f"实例异常结束: {e}\n")
            finally:
                inst.running = False
                def _mark_stopped():
                    try:
                        keys = list(self.instances.keys())
                        idx = keys.index(inst.id)
                        self.listbox.delete(idx)
                        self.listbox.insert(idx, f"{inst.name} (id:{inst.id}) [stopped]")
                    except Exception:
                        pass
                self.root.after(1, _mark_stopped)

        t = threading.Thread(target=target, daemon=True)
        inst.thread = t
        t.start()

    def start_instance(self):
        """从 UI 表单构建参数并启动新实例"""
        args = self.build_args()
        self._start_instance_with_args(args)

    def _start_instance_with_args(self, args):
        """内部方法：用指定的 args 创建实例并启动"""
        name = args.config
        iid = self.next_id
        self.next_id += 1
        inst = InstanceEntry(iid, name, args)
        self.instances[iid] = inst

        display_name = f"{name} (id:{iid}) [starting]"
        self.listbox.insert(tk.END, display_name)

        self._launch_instance_thread(inst)

    def get_selected_instance(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        idx = sel[0]
        try:
            iid = list(self.instances.keys())[idx]
            return self.instances.get(iid)
        except Exception:
            return None

    def on_select(self, event=None):
        inst = self.get_selected_instance()
        self.txt_log['state'] = 'normal'
        self.txt_log.delete('1.0', tk.END)
        if inst:
            self.txt_log.insert(tk.END, ''.join(inst.logs))
        self.txt_log['state'] = 'disabled'

    def stop_selected(self):
        inst = self.get_selected_instance()
        if not inst:
            messagebox.showinfo('Info', '未选择实例')
            return
        inst.stop_event.set()

    def stop_all(self):
        for inst in self.instances.values():
            inst.stop_event.set()

    def restart_selected(self):
        inst = self.get_selected_instance()
        if not inst:
            messagebox.showinfo('Info', '未选择实例')
            return
        
        # 先停止实例（如果未停止）
        if inst.running:
            inst.stop_event.set()
            # 等待实例停止（最多等 3 秒）
            for _ in range(30):
                if not inst.running:
                    break
                threading.Event().wait(0.1)
        
        # 使用相同参数启动新实例
        self._start_instance_with_args(inst.args)

    def clear_logs(self):
        inst = self.get_selected_instance()
        if not inst:
            return
        inst.logs = []
        self.txt_log['state'] = 'normal'
        self.txt_log.delete('1.0', tk.END)
        self.txt_log['state'] = 'disabled'


def main():
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()


if __name__ == '__main__':
    main()
