import pyautogui
import time

class AutoOperator:
    def __init__(self, operateDict : dict, configPath : str, loop : bool = False, printLog : bool = False):
        self._operateDict = operateDict
        self._operateIndex = 1
        self._configPath = configPath
        self._loop = loop
        self._printLog = printLog

    def Update(self) -> bool:
        operation = self._operateDict[self._operateIndex]

        operationWait, indexChangeFunc = self.Operate(operation)
        if operationWait and operationWait > 0:
            time.sleep(operationWait)
        elif 'wait' in operation:
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
        try:
            confidence = 0.8 if not "confidence" in operation else operation['confidence']
            region = None if not 'pic_region' in operation else operation['pic_region']

            if self._printLog:
                startTime = time.time()

            center = pyautogui.locateCenterOnScreen(f'{self._configPath}/{operation["search_pic"]}', confidence=confidence, region=region)            

            if self._printLog:
                print(f'搜索图片 {operation["search_pic"]}用时: {time.time()-startTime:.2f},位置: {center}')
        except pyautogui.ImageNotFoundException:
            if self._printLog:
                print(f'搜索图片 {operation["search_pic"]}未找到')
            return 1 if not 'pic_retry_time' in operation else operation['pic_retry_time'], lambda x : x
        except Exception as e:
            raise e
        else:
            if self._printLog:
                print(f'搜索图片 中心位置: {center}')
            if not 'operate_param' in operation:
                pyautogui.moveTo(center)

            return None, None

    def Operate(self, operation:dict):
        operationWait = None
        indexChangeFunc = None
        try:
            operateParam = None if not 'operate_param' in operation else operation['operate_param']
            match operation['operate']:
                case 'click':
                    if operateParam:
                        pyautogui.click(button=operateParam)
                    else:
                        pyautogui.click()                    
                case 'mDown':
                    if operateParam:
                        pyautogui.mouseDown(button=operateParam)
                    else:
                        pyautogui.mouseDown()                                        
                case 'mUp':
                    if operateParam:
                        pyautogui.mouseUp(button=operateParam)
                    else:
                        pyautogui.mouseUp()                                       
                case 'mMove':
                    if operateParam:
                        offset = operateParam.split(";")
                        pyautogui.moveRel(xOffset=float(offset[0]), yOffset=float(offset[1]))
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'mMoveTo':
                    if operateParam:
                        offset = operateParam.split(";")
                        pyautogui.moveTo(xOffset=float(offset[0]), yOffset=float(offset[1]))
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'press':
                    if operateParam:
                        pyautogui.press(operateParam)
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'kDown':
                    if operateParam:
                        pyautogui.keyDown(operateParam)
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'kUp':
                    if operateParam:
                        pyautogui.keyUp(operateParam)
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'write':
                    if operateParam:
                        param = operateParam.split(";")
                        if len(param) == 1:
                            pyautogui.write(param[0])
                        elif len(param) == 2:
                            pyautogui.write(param[0], interval=float(param[1]))
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'pic':
                    operationWait, indexChangeFunc = self.SearchPic(operation)

            if self._printLog:
                print(f'操作: {operation["operate"]}, 参数: {operateParam}')

        except Exception as e:
            raise e

        return operationWait, indexChangeFunc