import string
import win32gui
import win32ui
import win32api
import win32con
import time
import ctypes
import numpy as np
import cv2
import pyautogui
import pyscreeze
from .baseInput import BaseInput

# https://docs.microsoft.com/zh/windows/win32/inputdev/virtual-key-codes
# key的wparam就是vkcode
VkCode = {
    "back": 0x08,
    "tab": 0x09,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capital": 0x14,
    "esc": 0x1B,
    "space": 0x20,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "print": 0x2A,
    "snapshot": 0x2C,
    "insert": 0x2D,
    "delete": 0x2E,
    "lwin": 0x5B,
    "rwin": 0x5C,
    "numpad0": 0x60,
    "numpad1": 0x61,
    "numpad2": 0x62,
    "numpad3": 0x63,
    "numpad4": 0x64,
    "numpad5": 0x65,
    "numpad6": 0x66,
    "numpad7": 0x67,
    "numpad8": 0x68,
    "numpad9": 0x69,
    "multiply": 0x6A,
    "add": 0x6B,
    "separator": 0x6C,
    "subtract": 0x6D,
    "decimal": 0x6E,
    "divide": 0x6F,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
    "numlock": 0x90,
    "scroll": 0x91,
    "lshift": 0xA0,
    "rshift": 0xA1,
    "lcontrol": 0xA2,
    "rcontrol": 0xA3,
    "lmenu": 0xA4,
    "rmenu": 0XA5
}
# https://learn.microsoft.com/zh-cn/windows/win32/inputdev/mouse-input-notifications
WmCode = {
    "left_down": 0x0201,
    "left_up": 0x0202,
    "middle_down": 0x0207,
    "middle_up": 0x0208,
    "right_down": 0x0204,
    "right_up": 0x0205,
    "x1_down": 0x020B,
    "x1_up": 0x020C,
    "x2_down": 0x020B,
    "x2_up": 0x020C,
    "key_down": 0x0100,
    "key_up": 0x0101,
    "mouse_move": 0x0200,
    "mouse_wheel": 0x020A,
}
MwParam = {
    "left": 0x0001,
    "right": 0x0002,
    "middle": 0x0010,
    "x1": 0x0020,
    "x2": 0x0040,
}
MHwParam = {
    "x1": 0x0001,  # 侧键后退按钮
    "x2": 0x0002,  # 侧键前进按钮
}
PRIMARY = "left"
PRESS_TIME = 0.02
SAVE_SCREENSHOT_PATH = None
SAVE_SCREENSHOT = False

class BackGroundInput(BaseInput):
    def __init__(self, window_title: str, multi_window = False, print_log=False):
        self._window_title = window_title
        self._multi_window = multi_window
        self._pring_log = print_log
        hwnd = win32gui.FindWindow(None, window_title)  # 获取窗口句柄
        if hwnd:
            self._hwnd = hwnd
            
            # left, top, right, bottom = win32gui.GetClientRect(self._hwnd)
            # self._width = right - left
            # self._height = bottom - top
            window_left, window_top, window_right, window_bottom = win32gui.GetWindowRect(self._hwnd)
            self._window_left = window_left
            self._window_top = window_top
            self._window_width = window_right - window_left
            self._window_height = window_bottom - window_top
            self._screen_width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
            self._screen_height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
            self._is_fullscreen = (self._window_width == self._screen_width and self._window_height == self._screen_height)
            if not self._is_fullscreen:
                self._window_left += 8
                self._window_top += 8

            self._mouse_x = int(self._screen_width // 2)
            self._mouse_y = int(self._screen_height // 2)
        else:
            print(f"未找到窗口: {window_title}")
            return None
    
    def findWindowRecursive(self, parent_hwnd, class_name):
        result_hwnd = [None]  # 使用列表来在回调函数中传递引用

        def callback(hwnd, _):
            # 如果已经找到了，就没必要继续遍历了
            if result_hwnd[0] is not None:
                return
            
            # 检查当前子窗口的类名
            current_class = win32gui.GetClassName(hwnd)
            # print(f"  正在检查句柄 {hwnd}，类名: {current_class}") # 调试时可以取消注释
            
            if current_class == class_name:
                result_hwnd[0] = hwnd # 找到了！
            else:
                # 没找到，继续深入搜索这个子窗口的后代
                # 注意：不能直接在这里递归，EnumChildWindows会处理所有同级，
                pass
            return True # 继续枚举

        # 优先在直接子级中查找
        win32gui.EnumChildWindows(parent_hwnd, callback, None)
        if result_hwnd[0]:
            return result_hwnd[0]

        # 如果直接子级没找到，则对每个直接子级进行递归
        child_hwnds = []
        win32gui.EnumChildWindows(parent_hwnd, lambda hwnd, param: param.append(hwnd), child_hwnds)
        
        for child_hwnd in child_hwnds:
            found_hwnd = self.findWindowRecursive(child_hwnd, class_name)
            if found_hwnd:
                return found_hwnd
                
        return None

    def findSameNameWindowRecursive(self, parent_hwnd, class_name, index):
        hwnds = self.findAllWindowsRecursive(parent_hwnd, class_name)
        if len(hwnds) > index:
            return hwnds[index]
        
        return None

    def findAllWindowsRecursive(self, parent_hwnd, class_name):
        hwnds = []
        
        # 查找所有直接子窗口
        child_hwnds = []
        win32gui.EnumChildWindows(parent_hwnd, lambda hwnd, param: param.append(hwnd), child_hwnds)

        for hwnd in child_hwnds:
            # 检查当前子窗口的类名
            if win32gui.GetClassName(hwnd) == class_name:
                hwnds.append(hwnd)
            
            # 无论当前是否匹配，都继续深入其后代进行查找
            hwnds.extend(self.findAllWindowsRecursive(hwnd, class_name))
            
        return hwnds
        
    def findWindowAtPos(self, parent_hwnd, target_point):
        # 1. 转换坐标系：从父窗口客户区坐标到屏幕绝对坐标
        try:
            screen_point = (target_point[0] + self._window_left, target_point[1] + self._window_top)
        except win32gui.error:
            print(f"警告: 无法将坐标 {target_point} 转换为屏幕坐标。父窗口可能已失效。")
            return None

        # 2. 递归枚举所有后代，并筛选出所有可能的候选者
        candidates = []
        
        def enum_child_proc(hwnd, lparam):
            try:
                # a. 必须是可见且启用的窗口
                if not win32gui.IsWindowVisible(hwnd) or not win32gui.IsWindowEnabled(hwnd):
                    return True
                
                # b. 获取控件的屏幕矩形
                rect = win32gui.GetWindowRect(hwnd)
                
                # c. 检查点是否在矩形内
                if win32gui.PtInRect(rect, screen_point):
                    # 如果点在矩形内，计算其面积并将其作为候选者
                    width = rect[2] - rect[0]
                    height = rect[3] - rect[1]
                    area = width * height
                    candidates.append((hwnd, area)) # 存储 (句柄, 面积)
            except win32gui.error:
                # 忽略没有权限访问或已经销毁的窗口
                pass
            return True # 继续枚举

        try:
            win32gui.EnumChildWindows(parent_hwnd, enum_child_proc, None)
        except win32gui.error:
            pass # 如果父窗口本身有问题，就此打住

        # 3. 筛选出“最佳”匹配项：面积最小的那个
        if not candidates:
            # 如果一个子控件都没找到，目标可能就是父窗口本身
            # 检查父窗口客户区是否包含该点
            try:
                rect = win32gui.GetWindowRect(parent_hwnd)
                if win32gui.PtInRect(rect, screen_point):
                    return parent_hwnd
            except win32gui.error:
                pass
            return None

        # 按面积从小到大排序
        candidates.sort(key=lambda x: x[1])
        
        # 返回面积最小的那个控件的句柄
        return candidates[0][0]

    def _multiWindowCheck(func):
        def wrapper(self : "BackGroundInput", *args, **kwargs):
            retVal = None
            if self._multi_window:
                origin_hwnd = self._hwnd
                origin_x, origin_y = self._mouse_x, self._mouse_y
                hwnd = self.findWindowAtPos(origin_hwnd, (self._mouse_x, self._mouse_y))
                if hwnd and hwnd > 0 and hwnd != origin_hwnd:
                    self._hwnd = hwnd
                    # screen_pos = win32gui.ClientToScreen(origin_hwnd, (self._mouse_x, self._mouse_y))
                    # self._mouse_x, self._mouse_y = win32gui.ScreenToClient(hwnd, screen_pos)
                    # 子控件还需要考虑裁剪吗
                    screen_pos = (self._mouse_x + self._window_left, self._mouse_y + self._window_top)
                    window_left, window_top, _, _ = win32gui.GetWindowRect(self._hwnd)
                    self._mouse_x = screen_pos[0] - window_left
                    self._mouse_y = screen_pos[1] - window_top
                retVal = func(self, *args, **kwargs)
                self._hwnd = origin_hwnd
                self._mouse_x, self._mouse_y = origin_x, origin_y
            else:
                retVal = func(self, *args, **kwargs)
            return retVal
        return wrapper

    def convertFindRegion(self, region):
        if region is None:
            return None
        return (region[0] - self._window_left, region[1] - self._window_top, region[2], region[3])

    def locateCenterOnScreen(self, img, **kwargs):
        # self.activate()
        screenshotIm = self.screenShot()
        if 'region' in kwargs:
            region = kwargs['region']
            region = self.convertFindRegion(region)
            kwargs['region'] = region

            if SAVE_SCREENSHOT:
                crop_image = screenshotIm[region[1] : region[1] + region[3], region[0] : region[0] + region[2]]
                self.SaveScreenshot('screenshot_crop', crop_image)
        retVal = pyautogui.locate(img, screenshotIm, **kwargs)

        if retVal:
            return pyautogui.center(retVal)

    def screenShot(self):
        # win32gui.SetForegroundWindow(self._hwnd)
        # time.sleep(0.1)  # 给窗口一些时间响应
        # 获取设备上下文
        hwnd_dc = win32gui.GetWindowDC(self._hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        # 创建位图对象
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, self._window_width, self._window_height)
        save_dc.SelectObject(bitmap)

        # 进行截图
        user32 = ctypes.windll.user32
        user32.PrintWindow(self._hwnd, save_dc.GetSafeHdc(), 2)  # PW_RENDERFULLCONTENT=2
        # 转换为 numpy 数组
        bmpinfo = bitmap.GetInfo()
        bmpstr = bitmap.GetBitmapBits(True)
        # img_size = np.frombuffer(bmpstr, dtype=np.uint8).size
        img = np.frombuffer(bmpstr, dtype=np.uint8).reshape((bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4))

        # 释放资源
        win32gui.DeleteObject(bitmap.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(self._hwnd, hwnd_dc)

        # OpenCV 处理
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        #全屏处理
        if not self._is_fullscreen:
            img = img[8:-8, 8:-8, :]

        if SAVE_SCREENSHOT:
            self.SaveScreenshot('screenshot', img)
        return img

    def activate(self):
        win32gui.PostMessage(self._hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)
        
    def deactivate(self):
        win32gui.PostMessage(self._hwnd, win32con.WM_ACTIVATE, win32con.WA_INACTIVE, 0)

    def moveTo(self, x, y, duration=0.0):
        # self.activate()
        self._mouse_x = int(x)
        self._mouse_y = int(y)
        # wparam = 0
        # lparam = y << 16 | x
        # win32gui.PostMessage(self._hwnd, WmCode['mouse_move'], wparam, lparam)
        # self.deactivate()

    def moveRel(self, xOffset, yOffset, duration=None):
        self._mouse_x += int(xOffset)
        self._mouse_y += int(yOffset)

    def click(self, button=PRIMARY):
        # win32api.SetCursorPos((self._mouse_x, self._mouse_y))
        self.mouseDown(button)
        time.sleep(PRESS_TIME)
        self.mouseUp(button)

    @_multiWindowCheck
    def mouseDown(self, button=PRIMARY):
        self.activate()
        wparam = MwParam[button]
        if button in ["x1", "x2"]:
            wparam = wparam | MHwParam[button] << 16
        lparam = self._mouse_y << 16 | self._mouse_x
        message = WmCode[f"{button}_down"]
        win32gui.PostMessage(self._hwnd, message, wparam, lparam)
        self.deactivate()

    @_multiWindowCheck
    def mouseUp(self, button=PRIMARY):
        self.activate()
        wparam = 0
        if button in ["x1", "x2"]:
            wparam = wparam | MHwParam[button] << 16
        lparam = self._mouse_y << 16 | self._mouse_x
        message = WmCode[f"{button}_up"]
        win32gui.PostMessage(self._hwnd, message, wparam, lparam)
        self.deactivate()

    def virtualKeyCode(self, key: str):
        # 获取打印字符
        if len(key) == 1 and key in string.printable:
            # https://docs.microsoft.com/zh/windows/win32/api/winuser/nf-winuser-vkkeyscana
            return ctypes.windll.user32.VkKeyScanA(ord(key)) & 0xff
        # 获取控制字符
        else:
            return VkCode[key]

    def press(self, key: str):
        self.keyDown(key)
        time.sleep(PRESS_TIME)
        self.keyUp(key)

    @_multiWindowCheck
    def keyDown(self, key: str):
        self.activate()
        vk_code = self.virtualKeyCode(key)
        scan_code = ctypes.windll.user32.MapVirtualKeyW(vk_code, 0)
        # https://docs.microsoft.com/en-us/windows/win32/inputdev/wm-keydown
        wparam = vk_code
        lparam = (scan_code << 16) | 1
        win32gui.PostMessage(self._hwnd, WmCode["key_down"], wparam, lparam)
        self.deactivate()

    @_multiWindowCheck
    def keyUp(self, key: str):
        self.activate()
        vk_code = self.virtualKeyCode(key)
        scan_code = ctypes.windll.user32.MapVirtualKeyW(vk_code, 0)
        # https://docs.microsoft.com/en-us/windows/win32/inputdev/wm-keydown
        wparam = vk_code
        lparam = (scan_code << 16) | 1
        win32gui.PostMessage(self._hwnd, WmCode["key_up"], wparam, lparam)
        self.deactivate()

    def SaveScreenshot(self, fileName: str, img):
        cv2.imwrite(f'{SAVE_SCREENSHOT_PATH}/{fileName}-{time.strftime("%m%d%H%M%S", time.localtime())}.png', img)