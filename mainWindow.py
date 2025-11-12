import threading
import argparse
import json
import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
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
    def __init__(self, root:tk.Tk):
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
        Tooltip(btn_start, "点击启动一个新的实例(以当前参数)")

        btn_stop = tk.Button(frm_top, text='Stop Selected', command=self.stop_selected)
        btn_stop.grid(row=5, column=1)
        Tooltip(btn_stop, "停止所选实例")

        btn_stop_all = tk.Button(frm_top, text='Stop All', command=self.stop_all)
        btn_stop_all.grid(row=5, column=2)
        Tooltip(btn_stop_all, "停止所有实例")

        btn_restart = tk.Button(frm_top, text='Restart Selected', command=self.restart_selected)
        btn_restart.grid(row=5, column=3)
        Tooltip(btn_restart, "重启所选实例(运行中则会先停止)")

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

        btn_clear = tk.Button(frm_bottom, text='Clear Instances', command=self.clear_instances)
        btn_clear.pack(side=tk.LEFT)
        Tooltip(btn_clear, "清空所有实例(停止并移除)")

        btn_reload_csv = tk.Button(frm_bottom, text='Reload CSV', command=self.reload_csv)
        btn_reload_csv.pack(side=tk.LEFT, padx=6)
        Tooltip(btn_reload_csv, "重新加载所有 CSV 文件")

        btn_save = tk.Button(frm_bottom, text='Save Params', command=self.save_params)
        btn_save.pack(side=tk.LEFT, padx=6)
        Tooltip(btn_save, "保存当前参数到 JSON 文件")

        btn_load = tk.Button(frm_bottom, text='Load Params', command=self.load_params)
        btn_load.pack(side=tk.LEFT)
        Tooltip(btn_load, "从 JSON 文件加载参数")

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
                    # 检查当前视图是否处于底部（用户正在查看最新日志），
                    try:
                        yview = self.txt_log.yview()
                        at_bottom = (yview[1] >= 0.999)
                    except Exception:
                        at_bottom = True

                    self.txt_log.insert(tk.END, msg)
                    if at_bottom:
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

    def clear_instances(self):
        """清空所有 instances（停止并移除）"""
        if not self.instances:
            messagebox.showinfo('Info', '没有实例可清理')
            return
        
        # 确认操作
        if messagebox.askyesno('确认', '确定要清空所有实例吗？'):
            # 停止所有实例
            for inst in self.instances.values():
                inst.stop_event.set()
            # 清空实例列表
            self.instances.clear()
            self.next_id = 1
            # 更新 UI
            self.listbox.delete(0, tk.END)
            self.txt_log['state'] = 'normal'
            self.txt_log.delete('1.0', tk.END)
            self.txt_log['state'] = 'disabled'
            # messagebox.showinfo('完成', '所有实例已清空')

    def save_params(self):
        """让用户选择文件名并将当前参数保存为 JSON"""
        args = self.build_args()
        data = {
            'config': args.config,
            'loop': args.loop,
            'log': args.log,
            'screenshots': args.screenshots,
            'scale': args.scale,
            'scale_image': args.scale_image,
            'offset': args.offset,
            'title': args.title,
            'multi_window': args.multi_window,
            'process': args.process,
            'record': args.record,
        }

        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')], title='保存参数为 JSON')
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # messagebox.showinfo('保存成功', f'参数已保存到:\n{path}')
        except Exception as e:
            messagebox.showerror('保存失败', f'无法保存参数: {e}')

    def load_params(self):
        """从 JSON 文件加载参数并应用到界面"""
        path = filedialog.askopenfilename(filetypes=[('JSON', '*.json')], title='选择参数 JSON 文件')
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror('读取失败', f'无法读取文件: {e}')
            return

        # 应用各参数（存在性与类型安全检查）
        try:
            if 'config' in data:
                self.e_config.delete(0, tk.END)
                self.e_config.insert(0, str(data.get('config','')))

            if 'loop' in data:
                self.var_loop.set(bool(data.get('loop')))

            if 'log' in data:
                self.var_log.set(bool(data.get('log')))

            if 'screenshots' in data:
                self.var_screenshots.set(bool(data.get('screenshots')))

            if 'scale' in data:
                self.e_scale.delete(0, tk.END)
                self.e_scale.insert(0, str(data.get('scale')))

            if 'scale_image' in data:
                self.var_scale_image.set(bool(data.get('scale_image')))

            if 'offset' in data:
                self.e_offset.delete(0, tk.END)
                self.e_offset.insert(0, str(data.get('offset')))

            if 'title' in data:
                self.e_title.delete(0, tk.END)
                if data.get('title'):
                    self.e_title.insert(0, str(data.get('title')))

            if 'multi_window' in data:
                self.var_multi.set(bool(data.get('multi_window')))

            if 'process' in data:
                self.var_process.set(bool(data.get('process')))

            if 'record' in data:
                self.var_record.set(bool(data.get('record')))

            # messagebox.showinfo('加载成功', '参数已从文件应用')
        except Exception as e:
            messagebox.showerror('应用失败', f'无法应用参数: {e}')
    
    def reload_csv(self):
        """重新加载 main.csv 文件"""
        try:
            import autogui.parser as parser
            if messagebox.askyesno('确认', '重载CSV需要停止所有实例，是否继续？'):
                self.stop_all()
                parser.csvDataDict.clear()
                # messagebox.showinfo('加载成功', 'CSV已重新加载')
        except Exception as e:
            messagebox.showerror('重载失败')


class Tooltip:
    def __init__(self, widget:tk.Widget, text=None, delay=500, wraplength=300):
        """
        widget: 要绑定的 widget
        text: 字符串或可调用（返回字符串）用于动态文本
        delay: 毫秒，鼠标悬停多久显示提示
        wraplength: 提示文本自动换行宽度（像素）
        """
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wraplength = wraplength
        self._job = None
        self._tipwindow = None

        widget.bind('<Enter>', self._on_enter, add=True)
        widget.bind('<Leave>', self._on_leave, add=True)
        widget.bind('<Motion>', self._on_motion, add=True)  # 更新位置 / 动态文本

    def _on_enter(self, event=None):
        self._schedule()

    def _on_leave(self, event=None):
        self._unschedule()
        self._hide()

    def _on_motion(self, event=None):
        # 鼠标在控件上移动时（可以重新调度或更新位置）
        if self._tipwindow:
            self._reposition(event)

    def _schedule(self):
        self._unschedule()
        self._job = self.widget.after(self.delay, self._show)

    def _unschedule(self):
        if self._job:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _get_text(self):
        if callable(self.text):
            try:
                return str(self.text())
            except Exception:
                return ''
        return str(self.text or '')

    def _show(self):
        if self._tipwindow or not self.widget.winfo_ismapped():
            return
        text = self._get_text()
        if not text:
            return

        # 创建无边框的 Toplevel 作为 tooltip
        self._tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes('-topmost', True)

        # 样式
        label = tk.Label(tw, text=text, justify=tk.LEFT, background='#ffffff',
                         relief=tk.SOLID, borderwidth=1, wraplength=self.wraplength)
        label.pack(ipadx=4, ipady=2)

        # 初始定位
        try:
            x, y = self.widget.winfo_pointerxy()
            tw.wm_geometry(f"+{x + 16}+{y + 16}")
        except Exception:
            # 退回到 widget 位置
            x = self.widget.winfo_rootx()
            y = self.widget.winfo_rooty()
            tw.wm_geometry(f"+{x+16}+{y+16}")

    def _reposition(self, event=None):
        if not self._tipwindow:
            return
        try:
            x, y = self.widget.winfo_pointerxy()
            self._tipwindow.wm_geometry(f"+{x + 16}+{y + 16}")
        except Exception:
            pass

    def _hide(self):
        if self._tipwindow:
            try:
                self._tipwindow.destroy()
            except Exception:
                pass
            self._tipwindow = None


def main():
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()


if __name__ == '__main__':
    main()
