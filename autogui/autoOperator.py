import pyautogui
import pydirectinput
import pyperclip
import time
import random
from .scaleHelper import ScaleHelper
from .parser import GetCsv
from .ocr import OCR

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

            img = ScaleHelper.Instance().getScaleImg(f'{self._configPath}/{operation["search_pic"]}')
            center = pyautogui.locateCenterOnScreen(img, confidence=confidence, region=region)            

            if self._printLog:
                print(f'搜索图片 {operation["search_pic"]}, 用时: {time.time()-startTime:.2f},位置: {center}')
        except pyautogui.ImageNotFoundException:
            if self._printLog:
                print(f'搜索图片 {operation["search_pic"]} 未找到, 用时: {time.time()-startTime:.2f}')
            
            if operateParam:
                param = operateParam.split(";")

                match param[0]:
                    case 'notExist':
                        if self._printLog:
                            print(f'启动配置 {param[1]}')
                        self._subOperatorList.append(AutoOperator(GetCsv(self._configPath, param[1]), self._configPath, self._subOperatorList, False, self._printLog))

                        return None, lambda x : x, None

                    case 'exist':
                        return None, None, None

            return 1 if not 'pic_retry_time' in operation else operation['pic_retry_time'], lambda x : x, None if not 'pic_retry_time_random' in operation else operation['pic_retry_time_random']
        except Exception as e:
            raise e
        else:
            if not operateParam:
                # pyautogui.moveTo(center)
                pydirectinput.moveTo(center.x, center.y)
            else:
                param = operateParam.split(";")
                if param[0] == 'exist':
                    if self._printLog:
                        print(f'启动配置 {param[1]}')
                    self._subOperatorList.append(AutoOperator(GetCsv(self._configPath, param[1]), self._configPath, self._subOperatorList, False, self._printLog))
                    
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

        xCenter, yCenter = OCR(operation["search_pic"], region, confidence)            

        if xCenter is None or yCenter is None:
            if self._printLog:
                print(f'ocr {operation["search_pic"]} 未找到, 用时: {time.time()-startTime:.2f}')

            if operateParam:
                param = operateParam.split(";")

                match param[0]:
                    case 'notExist':
                        if self._printLog:
                            print(f'启动配置 {param[1]}')
                        self._subOperatorList.append(AutoOperator(GetCsv(self._configPath, param[1]), self._configPath, self._subOperatorList, False, self._printLog))

                        return None, lambda x : x, None

                    case 'exist':
                        return None, None, None

            return 1 if not 'pic_retry_time' in operation else operation['pic_retry_time'], lambda x : x, None if not 'pic_retry_time_random' in operation else operation['pic_retry_time_random']
        else:
            if self._printLog:
                print(f'ocr {operation["search_pic"]}, 用时: {time.time()-startTime:.2f}, 位置: {xCenter},{yCenter}')

            if not operateParam:
                # pyautogui.moveTo(xCenter, yCenter)
                pydirectinput.moveTo(xCenter, yCenter)
            else:
                param = operateParam.split(";")
                if param[0] == 'exist':
                    if self._printLog:
                        print(f'启动配置 {param[1]}')
                    self._subOperatorList.append(AutoOperator(GetCsv(self._configPath, param[1]), self._configPath, self._subOperatorList, False, self._printLog))
                    
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
                        # pyautogui.click(button=operateParam)
                        pydirectinput.click(button=operateParam)
                    else:
                        # pyautogui.click()                    
                        pydirectinput.click()
                case 'mDown':
                    if operateParam:
                        # pyautogui.mouseDown(button=operateParam)
                        pydirectinput.mouseDown(button=operateParam)
                    else:
                        # pyautogui.mouseDown()                                        
                        pydirectinput.mouseDown()                                        
                case 'mUp':
                    if operateParam:
                        # pyautogui.mouseUp(button=operateParam)
                        pydirectinput.mouseUp(button=operateParam)
                    else:
                        # pyautogui.mouseUp()                                       
                        pydirectinput.mouseUp()                                       
                case 'mMove':
                    if operateParam:
                        offset = operateParam.split(";")
                        # pyautogui.moveRel(xOffset=float(offset[0]), yOffset=float(offset[1]))
                        pydirectinput.moveRel(xOffset=ScaleHelper.Instance().getScaleInt(int(offset[0])), yOffset=ScaleHelper.Instance().getScaleInt(int(offset[1])))
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'mMoveTo':
                    if operateParam:
                        offset = operateParam.split(";")
                        # pyautogui.moveTo(x=float(offset[0]), y=float(offset[1]))
                        pos = ScaleHelper.Instance().getScalePos((int(offset[0]), int(offset[1])))
                        pydirectinput.moveTo(x=pos[0], y=pos[1])
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'press':
                    if operateParam:
                        # pyautogui.press(operateParam)
                        pydirectinput.press(operateParam)
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'kDown':
                    if operateParam:
                        # pyautogui.keyDown(operateParam)
                        pydirectinput.keyDown(operateParam)
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'kUp':
                    if operateParam:
                        # pyautogui.keyUp(operateParam)
                        pydirectinput.keyUp(operateParam)
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