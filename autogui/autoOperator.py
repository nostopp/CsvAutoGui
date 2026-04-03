import pyautogui
import pydirectinput
import pyperclip
import time
import random
import numpy as np
import re
import threading
from pathlib import Path
from . import log
from . import notifier
from .scaleHelper import ScaleHelper
from .parser import GetCsv
from .ocr import OCR
from .baseInput import BaseInput

CONFIDENCE_PATTERN = re.compile(r'confidence\s*=\s*([\d.-]+)')

class AutoOperator:
    def __init__(self, operateDict : dict, configPath : str, subOperatorList:list, input:BaseInput, scaleHelper : ScaleHelper,  loop : bool = False, printLog : bool = False):
        self._operateDict = operateDict
        self._operateIndex = 1
        self._configPath = configPath
        self._subOperatorList = subOperatorList
        self._input = input
        self._scaleHelper = scaleHelper
        self._loop = loop
        self._printLog = printLog
        self._jumpMarks = dict()
        for index, operation in operateDict.items():
            if 'jump_mark' in operation:
                self._jumpMarks[operation['jump_mark']] = index

    def _start_sub_operator(self, file_name: str):
        if self._printLog:
            log.debug(f'启动配置 {file_name}')
        self._subOperatorList.append(
            AutoOperator(
                GetCsv(self._configPath, self._scaleHelper, file_name),
                self._configPath,
                self._subOperatorList,
                self._input,
                self._scaleHelper,
                False,
                self._printLog,
            )
        )

    def _jump_to(self, target: int | str):
        jump = self.Jump(target)
        if self._printLog:
            log.debug(f'跳转 {target}, 实际跳转到 {jump}')
        return None, lambda x : jump, None

    def _handle_branch_result(self, operateParam, matched: bool):
        if not operateParam:
            return None

        trigger = operateParam[0]

        if matched:
            if trigger == 'exist':
                if len(operateParam) <= 2:
                    self._start_sub_operator(operateParam[1])
                    return None, None, None
                return self._jump_to(operateParam[1])

            if len(operateParam) <= 2:
                return None, None, None
            return self._jump_to(operateParam[2])

        if trigger == 'notExist':
            if len(operateParam) <= 2:
                self._start_sub_operator(operateParam[1])
                return None, None, None
            return self._jump_to(operateParam[1])

        if len(operateParam) <= 2:
            return None, None, None
        return self._jump_to(operateParam[2])

    def _move_to_match(self, operation:dict, center_x: int, center_y: int, width: int, height: int):
        if not 'pic_range_random' in operation:
            self._input.moveTo(center_x, center_y, operation.get('move_time', None))
            return

        startX = center_x - width / 2
        startY = center_y - height / 2
        self._input.moveTo(int(startX + random.random() * width), int(startY + random.random() * height), operation.get('move_time', None))

    def Update(self) -> bool:
        if len(self._operateDict) <= 0:
            return False

        operation = self._operateDict[self._operateIndex]

        operationWait, indexChangeFunc, operationWaitRandom = self.Operate(operation)
        waitTime = 0
        if operationWait and operationWait > 0:
            if not operationWaitRandom:
                waitTime = operationWait
            else:
                waitTime = operationWait + random.random()*operationWaitRandom
        elif 'wait' in operation:
            if 'wait_random' in operation:
                waitTime = operation['wait'] + random.random()*operation['wait_random']
            else:
                waitTime = operation['wait']
        if waitTime > 0:
            if self._printLog:
                log.debug(f'等待 {waitTime} s')
            time.sleep(waitTime)

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
            grayscale = False if 'disable_grayscale' in operation else None

            if not 'search_pic_cache' in operation:
                img_path = Path(self._configPath) / operation["search_pic"]
                img = self._scaleHelper.getScaleImg(img_path)
                operation['search_pic_cache'] = img
            else:
                img = operation['search_pic_cache']
            center = self._input.locateCenterOnScreen(img, confidence=confidence, region=region, grayscale=grayscale)

            if self._printLog:
                log.debug(f'搜索图片 {operation["search_pic"]}, 用时: {time.time()-startTime:.2f},位置: {center}')
        except pyautogui.ImageNotFoundException as e:
            if self._printLog:
                match = CONFIDENCE_PATTERN.search(str(e.__context__))
                if match:
                    log.debug(f'搜索图片 {operation["search_pic"]} 未找到, 用时: {time.time()-startTime:.2f}, 置信度: {match.group(1)}')
                else:
                    log.debug(f'搜索图片 {operation["search_pic"]} 未找到, 用时: {time.time()-startTime:.2f}')
            
            if operateParam:
                return self._handle_branch_result(operateParam, matched=False)

            return 1 if not 'pic_retry_time' in operation else operation['pic_retry_time'], lambda x : x, None if not 'pic_retry_time_random' in operation else operation['pic_retry_time_random']
        except Exception as e:
            raise e
        else:
            if not operateParam:
                height, width = img.shape[:2]
                self._move_to_match(operation, center.x, center.y, width, height)
            else:
                return self._handle_branch_result(operateParam, matched=True)

            return None, None, None

    def Ocr(self, operation:dict):
        operateParam = None if not 'operate_param' in operation else operation['operate_param']

        if self._printLog:
            startTime = time.time()
        
        confidence = 0.9 if not "confidence" in operation else operation['confidence']
        region = None if not 'pic_region' in operation else operation['pic_region']

        if self._printLog:
            startTime = time.time()

        xCenter, yCenter, width, height = OCR(operation["search_pic"], self._input, region, confidence)            

        if xCenter is None or yCenter is None:
            if self._printLog:
                log.debug(f'ocr {operation["search_pic"]} 未找到, 用时: {time.time()-startTime:.2f}')

            if operateParam:
                return self._handle_branch_result(operateParam, matched=False)

            return 1 if not 'pic_retry_time' in operation else operation['pic_retry_time'], lambda x : x, None if not 'pic_retry_time_random' in operation else operation['pic_retry_time_random']
        else:
            if self._printLog:
                log.debug(f'ocr {operation["search_pic"]}, 用时: {time.time()-startTime:.2f}, 位置: {xCenter},{yCenter}')

            if not operateParam:
                self._move_to_match(operation, xCenter, yCenter, width, height)
            else:
                return self._handle_branch_result(operateParam, matched=True)

            return None, None, None

    def Operate(self, operation:dict):
        operationWait = None
        indexChangeFunc = None
        operationWaitRandom = None
        try:
            operateParam = None if not 'operate_param' in operation else operation['operate_param']
            if self._printLog:
                log.debug(f'操作: {operation["operate"]}, 参数: {operateParam}')
            match operation['operate']:
                case 'click':
                    if operateParam:
                        self._input.click(button=operateParam)
                    else:
                        self._input.click()
                case 'mDown':
                    if operateParam:
                        self._input.mouseDown(button=operateParam)
                    else:
                        self._input.mouseDown()
                case 'mUp':
                    if operateParam:
                        self._input.mouseUp(button=operateParam)
                    else:
                        self._input.mouseUp()
                case 'mMove':
                    if operateParam:
                        self._input.moveRel(operateParam[0], operateParam[1], operation.get('move_time', None))
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'mMoveTo':
                    if operateParam:
                        self._input.moveTo(operateParam[0], operateParam[1], operation.get('move_time', None))
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'press':
                    if operateParam:
                        self._input.press(operateParam)
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'kDown':
                    if operateParam:
                        self._input.keyDown(operateParam)
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'kUp':
                    if operateParam:
                        self._input.keyUp(operateParam)
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'write':
                    if operateParam:
                        pyperclip.copy(operateParam)
                        self._input.hotkey('ctrl', 'v')
                    else:
                        raise Exception(f"{operation['index']},{operation['operate']} 操作参数错误")
                case 'pic':
                    operationWait, indexChangeFunc, operationWaitRandom = self.SearchPic(operation)
                case 'ocr':
                    operationWait, indexChangeFunc, operationWaitRandom = self.Ocr(operation)
                case 'notify':
                    notifier.notify(operateParam, beep=True)
                case 'jmp':
                    jmp = self.Jump(operateParam)
                    if self._printLog:
                        log.debug(f'跳转 {operateParam}, 实际跳转到 {jmp}')
                    return None, lambda x : jmp, None

        except Exception as e:
            raise e

        return operationWait, indexChangeFunc, operationWaitRandom

    def Jump(self, target:int|str):
        if target in self._jumpMarks:
            return self._jumpMarks[target]
        else:
            return target