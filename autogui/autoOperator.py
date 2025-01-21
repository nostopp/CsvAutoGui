import pyautogui
import time

class AutoOperator:
    def __init__(self, operateDict : dict, configPath : str, loop : bool = False):
        self._operateDict = operateDict
        self._operateIndex = 1
        self._configPath = configPath
        self._loop = loop

    def Update(self) -> bool:
        operation = self._operateDict[self._operateIndex]
        if 'search_pic' in operation:
            if not self.SearchPic(operation):
                time.sleep(1)
                return
            else:
                self.Operate(operation)
        else:
            self.Operate(operation)
        if 'wait' in operation:
            time.sleep(operation['wait'])

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

            startTime = time.time()
            center = pyautogui.locateCenterOnScreen(f'{self._configPath}/{operation["search_pic"]}', confidence=confidence, region=region)            
            print(f'搜索图片{operation["search_pic"]}用时: {time.time()-startTime}')
        except pyautogui.ImageNotFoundException:
            return False
        except Exception as e:
            raise e
        else:
            pyautogui.moveTo(center)
            return True

    def Operate(self, operation:dict):
        try:
            match operation['operate']:
                case 'click':
                    if 'operate_param' in operation:
                        pyautogui.click(button=operation['operate_params'])
                    else:
                        pyautogui.click()                    
                case 'mDown':
                    if 'operate_param' in operation:
                        pyautogui.mouseDown(button=operation['operate_params'])
                    else:
                        pyautogui.mouseDown()                                        
                case 'mUp':
                    if operation['operate_param']:
                        pyautogui.mouseUp(button=operation['operate_params'])
                    else:
                        pyautogui.mouseUp()                                       
                case 'mMove':
                    if operation['operate_param']:
                        offset = operation['operate_params'].split(";")
                        pyautogui.moveRel(xOffset=float(offset[0]), yOffset=float(offset[1]))
                    else:
                        raise Exception(f"{operation['index']} 操作参数错误: {operation['operate_params']}")

        except Exception as e:
            raise e