import pyautogui
import pydirectinput
import pyperclip
import time
import random
import numpy as np
from .scaleHelper import ScaleHelper
from .parser import GetCsv
from .ocr import OCR

MOVE_FPS = 60
MOVE_INTERVAL = 1/MOVE_FPS

def continueMoveTo(start:np.array, end:np.array, duration):
    steps = max(1, int(duration * MOVE_FPS))
    delta = end - start
    start_time = time.perf_counter()
    for i in range(steps):
        t = (i + 1) / steps
        x = int(start[0] + delta[0] * t)
        y = int(start[1] + delta[1] * t)
        pydirectinput.moveTo(x, y, _pause=False)
        next_frame_time = start_time + (i + 1) * MOVE_INTERVAL
        now = time.perf_counter()
        sleep_time = next_frame_time - now
        if sleep_time > 0:
            time.sleep(sleep_time)
    # 最后确保到达终点
    # pydirectinput.moveTo(int(end[0]), int(end[1]), _pause=False)

def moveTo(x, y, duration=None):
    if not duration:
        pydirectinput.moveTo(x, y, _pause=False)
        return

    start = np.array(pydirectinput.position())
    end = np.array([x, y])
    continueMoveTo(start, end, duration)

def moveRel(xOffset, yOffset, duration=None):
    if not duration:
        pydirectinput.moveRel(xOffset, yOffset, _pause=False)
        return

    start = np.array(pydirectinput.position())
    end = start + np.array([xOffset, yOffset])
    continueMoveTo(start, end, duration)


class AutoOperator:
    def __init__(self, operateDict : dict, configPath : str, subOperatorList:list, loop : bool = False, printLog : bool = False):
        self._operateDict = operateDict
        self._operateIndex = 1
        self._configPath = configPath
        self._subOperatorList = subOperatorList
        self._loop = loop
        self._printLog = printLog

    def Update(self) -> bool:
        if len(self._operateDict) <= 0:
            return False

        operation = self._operateDict[self._operateIndex]

        operationWait, indexChangeFunc, operationWaitRandom = self.Operate(operation)
        if operationWait and operationWait > 0:
            if not operationWaitRandom:
                time.sleep(operationWait)
            else:
                time.sleep(operationWait + random.random()*operationWaitRandom)
        elif 'wait' in operation:
            if 'wait_random' in operation:
                time.sleep(operation['wait'] + random.random()*operation['wait_random'])
            else:
                time.sleep(operation['wait'])

        if indexChangeFunc:
            self._operateIndex = indexChangeFunc(self._operateIndex)
        else:
            self._operateIndex += 1
        if self._operateIndex > len(self._operateDict):
            if self._loop:
                self._operateIndex = 1
            else:
                return False
        
        return True


    def SearchPic(self, operation:dict):
        operateParam = None if not 'operate_param' in operation else operation['operate_param']
        if self._printLog:
            startTime = time.time()
        try:
            confidence = 0.8 if not "confidence" in operation else operation['confidence']
            region = None if not 'pic_region' in operation else operation['pic_region']

            if not 'search_pic_cache' in operation:
                img = ScaleHelper.Instance().getScaleImg(f'{self._configPath}/{operation["search_pic"]}')
                operation['search_pic_cache'] = img
            else:
                img = operation['search_pic_cache']
            center = pyautogui.locateCenterOnScreen(img, confidence=confidence, region=region)            

            if self._printLog:
                print(f'搜索图片 {operation["search_pic"]}, 用时: {time.time()-startTime:.2f},位置: {center}')
        except pyautogui.ImageNotFoundException:
            if self._printLog:
                print(f'搜索图片 {operation["search_pic"]} 未找到, 用时: {time.time()-startTime:.2f}')
            
            if operateParam:
                match operateParam[0]:
                    case 'notExist':
                        if self._printLog:
                            print(f'启动配置 {operateParam[1]}')
                        self._subOperatorList.append(AutoOperator(GetCsv(self._configPath, operateParam[1]), self._configPath, self._subOperatorList, False, self._printLog))

                        return None, lambda x : x, None

                    case 'exist':
                        return None, None, None

            return 1 if not 'pic_retry_time' in operation else operation['pic_retry_time'], lambda x : x, None if not 'pic_retry_time_random' in operation else operation['pic_retry_time_random']
        except Exception as e:
            raise e
        else:
            if not operateParam:
                if not 'pic_range_random' in operation:
                    moveTo(center.x, center.y, operation.get('move_time', None))
                else:
                    height, width = img.shape[:2]
                    startX = center.x - width / 2
                    startY = center.y - height / 2
                    moveTo(int(startX + random.random() * width), int(startY + random.random() * height), operation.get('move_time', None))
            else:
                if operateParam[0] == 'exist':
                    if self._printLog:
                        print(f'启动配置 {operateParam[1]}')
                    self._subOperatorList.append(AutoOperator(GetCsv(self._configPath, operateParam[1]), self._configPath, self._subOperatorList, False, self._printLog))
                    
                    return None, lambda x : x, None

            return None, None, None

    def Ocr(self, operation:dict):
        operateParam = None if not 'operate_param' in operation else operation['operate_param']

        if self._printLog:
            startTime = time.time()
        
        confidence = 0.9 if not "confidence" in operation else operation['confidence']
        region = None if not 'pic_region' in operation else operation['pic_region']

        if self._printLog:
            startTime = time.time()

        xCenter, yCenter, width, height = OCR(operation["search_pic"], region, confidence)            

        if xCenter is None or yCenter is None:
            if self._printLog:
                print(f'ocr {operation["search_pic"]} 未找到, 用时: {time.time()-startTime:.2f}')

            if operateParam:
                match operateParam[0]:
                    case 'notExist':
                        if self._printLog:
                            print(f'启动配置 {operateParam[1]}')
                        self._subOperatorList.append(AutoOperator(GetCsv(self._configPath, operateParam[1]), self._configPath, self._subOperatorList, False, self._printLog))

                        return None, lambda x : x, None

                    case 'exist':
                        return None, None, None

            return 1 if not 'pic_retry_time' in operation else operation['pic_retry_time'], lambda x : x, None if not 'pic_retry_time_random' in operation else operation['pic_retry_time_random']
        else:
            if self._printLog:
                print(f'ocr {operation["search_pic"]}, 用时: {time.time()-startTime:.2f}, 位置: {xCenter},{yCenter}')

            if not operateParam:
                if not 'pic_range_random' in operation:
                    moveTo(xCenter, yCenter, operation.get('move_time', None))
                else:
                    startX = xCenter - width / 2
                    startY = yCenter - height / 2
                    moveTo(int(startX + random.random() * width), int(startY + random.random() * height), operation.get('move_time', None))
            else:
                if operateParam[0] == 'exist':
                    if self._printLog:
                        print(f'启动配置 {operateParam[1]}')
                    self._subOperatorList.append(AutoOperator(GetCsv(self._configPath, operateParam[1]), self._configPath, self._subOperatorList, False, self._printLog))
                    
                    return None, lambda x : x, None

            return None, None, None

    def Operate(self, operation:dict):
        operationWait = None
        indexChangeFunc = None
        operationWaitRandom = None
        try:
            operateParam = None if not 'operate_param' in operation else operation['operate_param']
            if self._printLog:
                print(f'操作: {operation["operate"]}, 参数: {operateParam}')
            match operation['operate']:
                case 'click':
                    if operateParam:
                        pydirectinput.click(button=operateParam, _pause=False)
                    else:
                        pydirectinput.click(_pause=False)
                case 'mDown':
                    if operateParam:
                        pydirectinput.mouseDown(button=operateParam, _pause=False)
                    else:
                        pydirectinput.mouseDown(_pause=False)                                        
                case 'mUp':
                    if operateParam:
                        pydirectinput.mouseUp(button=operateParam, _pause=False)
                    else:
                        pydirectinput.mouseUp(_pause=False)                                       
                case 'mMove':
                    if operateParam:
                        moveRel(operateParam[0], operateParam[1], operation.get('move_time', None))
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'mMoveTo':
                    if operateParam:
                        moveTo(operateParam[0], operateParam[1], operation.get('move_time', None))
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'press':
                    if operateParam:
                        pydirectinput.press(operateParam, _pause=False)
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'kDown':
                    if operateParam:
                        pydirectinput.keyDown(operateParam, _pause=False)
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'kUp':
                    if operateParam:
                        pydirectinput.keyUp(operateParam, _pause=False)
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'write':
                    if operateParam:
                        pyperclip.copy(operateParam)
                        pyautogui.hotkey('ctrl', 'v')
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'pic':
                    operationWait, indexChangeFunc, operationWaitRandom = self.SearchPic(operation)
                case 'ocr':
                    operationWait, indexChangeFunc, operationWaitRandom = self.Ocr(operation)
                case 'end':
                    indexChangeFunc = lambda x : len(self._operateDict) + 1

        except Exception as e:
            raise e

        return operationWait, indexChangeFunc, operationWaitRandom