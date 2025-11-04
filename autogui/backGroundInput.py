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
    "x1": 0x0001,  # 侧键后退按钮
    "x2": 0x0002,  # 侧键前进按钮
}
PRESS_TIME = 0.02
SAVE_SCREENSHOT_PATH = None
SAVE_SCREENSHOT = False

class BackGroundInput(BaseInput):
    def __init__(self, window_title: str):
        self._window_title = window_title
        hwnd = win32gui.FindWindow(None, window_title)  # 获取窗口句柄
        if hwnd:
            self._hwnd = hwnd
            
            left, top, right, bottom = win32gui.GetClientRect(self._hwnd)
            window_left, window_top, window_right, window_bottom = win32gui.GetWindowRect(self._hwnd)
            self._width = right - left
            self._height = bottom - top
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

            self._mouse_x = self._screen_width // 2
            self._mouse_y = self._screen_height // 2
        else:
            print(f"未找到窗口: {window_title}")
            return None

    def convertFindRegion(self, region):
        if region is None:
            return None
        return (region[0] - self._window_left, region[1] - self._window_top, region[2], region[3])

    def locateCenterOnScreen(self, img, **kwargs):
        try:
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
        except pyscreeze.ImageNotFoundException:
            raise

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

    def moveTo(self, x, y, duration=0.0):
        wparam = 0
        lparam = y << 16 | x
        self._mouse_x = x
        self._mouse_y = y
        win32gui.PostMessage(self._hwnd, WmCode['mouse_move'], wparam, lparam)

    def moveRel(self, xOffset, yOffset, duration=None):
        pass

    def click(self, button: str):
        # self.activate()
        self.mouseDown(button)
        time.sleep(PRESS_TIME)
        self.mouseUp(button)

    def mouseDown(self, button: str):
        wparam = 0
        if button in ["x1", "x2"]:
            wparam = MwParam[button]
        lparam = self._mouse_y << 16 | self._mouse_x
        message = WmCode[f"{button}_down"]
        win32gui.PostMessage(self._hwnd, message, wparam, int(lparam))

    def mouseUp(self, button: str):
        wparam = 0
        if button in ["x1", "x2"]:
            wparam = MwParam[button]
        lparam = self._mouse_y << 16 | self._mouse_x
        message = WmCode[f"{button}_up"]
        win32gui.PostMessage(self._hwnd, message, wparam, lparam)

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

    def keyDown(self, key: str):
        vk_code = self.virtualKeyCode(key)
        scan_code = ctypes.windll.user32.MapVirtualKeyW(vk_code, 0)
        # https://docs.microsoft.com/en-us/windows/win32/inputdev/wm-keydown
        wparam = vk_code
        lparam = (scan_code << 16) | 1
        win32gui.PostMessage(self._hwnd, WmCode["key_down"], wparam, lparam)

    def keyUp(self, key: str):
        vk_code = self.virtualKeyCode(key)
        scan_code = ctypes.windll.user32.MapVirtualKeyW(vk_code, 0)
        # https://docs.microsoft.com/en-us/windows/win32/inputdev/wm-keydown
        wparam = vk_code
        lparam = (scan_code << 16) | 1
        win32gui.PostMessage(self._hwnd, WmCode["key_up"], wparam, lparam)

    def SaveScreenshot(self, fileName: str, img):
        cv2.imwrite(f'{SAVE_SCREENSHOT_PATH}/{fileName}-{time.strftime("%m%d%H%M%S", time.localtime())}.png', img)