from __future__ import annotations

import pyautogui
import pyperclip
import time
import random
import re
from operation_contracts import (
    OperationType,
    is_terminal_jump_target,
    require_operation_contract,
)
from ..flow.models import CompiledFlow, CompiledOperation
from ..infrastructure import log
from ..notifications import runtime as notification_runtime
from ..runtime.context import RuntimeContext
from ..scripting.runtime import execute_script_node
from ..vision.ocr import OCR

CONFIDENCE_PATTERN = re.compile(r'confidence\s*=\s*([\d.-]+)')
PIC_DEFAULT_CONFIDENCE = require_operation_contract(OperationType.PIC).default_confidence
OCR_DEFAULT_CONFIDENCE = require_operation_contract(OperationType.OCR).default_confidence

class AutoOperator:
    def __init__(
        self,
        compiled_flow: CompiledFlow,
        runtime_context: RuntimeContext,
        sub_operator_list: list["AutoOperator"],
        loop: bool = False,
    ) -> None:
        if not isinstance(compiled_flow, CompiledFlow):
            raise TypeError("compiled_flow 必须是 CompiledFlow")
        self._compiled_flow = compiled_flow
        self._operations_by_index = compiled_flow.operations_by_index
        self._operations = compiled_flow.operations
        self._cursor = 0
        self._index_to_cursor = {
            operation.index: cursor
            for cursor, operation in enumerate(self._operations)
        }
        self._runtime_context = runtime_context
        self._sub_operator_list = sub_operator_list
        self._input = runtime_context.input
        self._loop = loop
        self._print_log = runtime_context.print_log
        self._source_file = compiled_flow.file_name
        self._jump_marks = dict(compiled_flow.jump_marks)

    @property
    def source_file(self) -> str:
        return self._source_file

    @property
    def has_current_operation(self) -> bool:
        return self._cursor < len(self._operations)

    def peek_current_operation(self) -> CompiledOperation:
        return self._operations[self._cursor]

    def _start_sub_operator(self, file_name: str):
        if file_name.lower().endswith('_resource.csv'):
            raise ValueError(f'资源文件不能作为子流程执行: {file_name}')
        if self._print_log:
            log.debug(f'启动配置 {file_name}')
        flow = self._runtime_context.get_compiled_flow(file_name)
        self._sub_operator_list.append(
            AutoOperator(
                flow,
                self._runtime_context,
                self._sub_operator_list,
            )
        )

    def _jump_to(self, target: int | str):
        jump = self.Jump(target)
        if self._print_log:
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

    def _move_to_match(self, operation: CompiledOperation, center_x: int, center_y: int, width: int, height: int):
        if not operation.range_random:
            self._input.moveTo(center_x, center_y, operation.move_time)
            return

        startX = center_x - width / 2
        startY = center_y - height / 2
        self._input.moveTo(int(startX + random.random() * width), int(startY + random.random() * height), operation.move_time)

    def _resolve_script_jump(self, target: int | str) -> int:
        jump = self.Jump(target)
        if is_terminal_jump_target(jump):
            return int(jump)
        if isinstance(jump, str):
            try:
                jump = int(jump)
            except Exception:
                pass

        if not isinstance(jump, int) or jump not in self._operations_by_index:
            raise KeyError(f'无效的跳转目标: {target}')

        return jump

    def _run_script(self, operation: CompiledOperation):
        return execute_script_node(
            operation.to_script_node_dict(),
            self._runtime_context,
            self._resolve_script_jump,
            self._start_sub_operator,
        )

    def Update(self) -> bool:
        if len(self._operations_by_index) <= 0:
            return False

        operation = self._operations[self._cursor]

        operationWait, indexChangeFunc, operationWaitRandom = self.Operate(operation)
        target_index = indexChangeFunc(operation.index) if indexChangeFunc else None
        if target_index is not None and is_terminal_jump_target(target_index):
            self._cursor = len(self._operations)
            return False

        waitTime = 0
        if operationWait and operationWait > 0:
            if not operationWaitRandom:
                waitTime = operationWait
            else:
                waitTime = operationWait + random.random()*operationWaitRandom
        elif operation.wait is not None:
            if operation.wait_random is not None:
                waitTime = operation.wait + random.random()*operation.wait_random
            else:
                waitTime = operation.wait
        if waitTime > 0:
            if self._print_log:
                log.debug(f'等待 {waitTime} s')
            time.sleep(waitTime)

        if target_index is not None:
            if target_index not in self._index_to_cursor:
                raise KeyError(f'无效的跳转目标: {target_index}')
            self._cursor = self._index_to_cursor[target_index]
        else:
            self._cursor += 1
        if self._cursor >= len(self._operations):
            if self._loop:
                self._cursor = 0
            else:
                return False
        
        return True


    def SearchPic(self, operation: CompiledOperation):
        operateParam = operation.operate_param
        if self._print_log:
            startTime = time.time()
        try:
            confidence = PIC_DEFAULT_CONFIDENCE if operation.confidence is None else operation.confidence
            region = operation.region
            grayscale = False if operation.disable_grayscale else None
            if operation.search_target is None:
                raise KeyError("search_pic")
            img = self._runtime_context.get_image(operation.search_target)
            center = self._input.locateCenterOnScreen(img, confidence=confidence, region=region, grayscale=grayscale)
            matchConfidence = getattr(self._input, '_last_locate_confidence', None)

            if self._print_log:
                confidenceText = '' if matchConfidence is None else f', 置信度: {matchConfidence:.3f}'
                log.debug(f'搜索图片 {operation.search_target}, 用时: {time.time()-startTime:.2f},位置: {center}{confidenceText}')
        except pyautogui.ImageNotFoundException as e:
            if self._print_log:
                matchConfidence = getattr(e, 'confidence_score', None)
                if matchConfidence is None:
                    matchConfidence = getattr(self._input, '_last_locate_confidence', None)
                if matchConfidence is None:
                    errorTexts = [str(e)]
                    if e.__context__:
                        errorTexts.append(str(e.__context__))
                    for errorText in errorTexts:
                        match = CONFIDENCE_PATTERN.search(errorText)
                        if match:
                            matchConfidence = float(match.group(1))
                            break

                confidenceText = '' if matchConfidence is None else f', 置信度: {matchConfidence:.3f}'
                log.debug(f'搜索图片 {operation.search_target} 未找到, 用时: {time.time()-startTime:.2f}{confidenceText}')

            if operateParam:
                return self._handle_branch_result(operateParam, matched=False)

            return 1 if operation.retry is None else operation.retry, lambda x : x, operation.retry_random
        else:
            if not operateParam:
                height, width = img.shape[:2]
                self._move_to_match(operation, center.x, center.y, width, height)
            else:
                return self._handle_branch_result(operateParam, matched=True)

            return None, None, None

    def Ocr(self, operation: CompiledOperation):
        operateParam = operation.operate_param

        if self._print_log:
            startTime = time.time()
        
        confidence = OCR_DEFAULT_CONFIDENCE if operation.confidence is None else operation.confidence
        region = operation.region

        if self._print_log:
            startTime = time.time()

        if operation.search_target is None:
            raise KeyError("search_pic")
        xCenter, yCenter, width, height = OCR(operation.search_target, self._input, region, confidence)

        if xCenter is None or yCenter is None:
            if self._print_log:
                log.debug(f'ocr {operation.search_target} 未找到, 用时: {time.time()-startTime:.2f}')

            if operateParam:
                return self._handle_branch_result(operateParam, matched=False)

            return 1 if operation.retry is None else operation.retry, lambda x : x, operation.retry_random
        else:
            if self._print_log:
                log.debug(f'ocr {operation.search_target}, 用时: {time.time()-startTime:.2f}, 位置: {xCenter},{yCenter}')

            if not operateParam:
                self._move_to_match(operation, xCenter, yCenter, width, height)
            else:
                return self._handle_branch_result(operateParam, matched=True)

            return None, None, None

    def Operate(self, operation: CompiledOperation):
        operationWait = None
        indexChangeFunc = None
        operationWaitRandom = None
        operateParam = operation.operate_param
        if self._print_log:
            log.debug(f'操作: {operation.operation}, 参数: {operateParam}')
        match operation.operation:
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
                    self._input.moveRel(operateParam[0], operateParam[1], operation.move_time)
                else:
                    raise Exception(f"{operation.index},{operation.operation} 操作参数错误")
            case 'mMoveTo':
                if operateParam:
                    self._input.moveTo(operateParam[0], operateParam[1], operation.move_time)
                else:
                    raise Exception(f"{operation.index},{operation.operation} 操作参数错误")
            case 'press':
                if operateParam:
                    self._input.press(operateParam)
                else:
                    raise Exception(f"{operation.index},{operation.operation} 操作参数错误")
            case 'kDown':
                if operateParam:
                    self._input.keyDown(operateParam)
                else:
                    raise Exception(f"{operation.index},{operation.operation} 操作参数错误")
            case 'kUp':
                if operateParam:
                    self._input.keyUp(operateParam)
                else:
                    raise Exception(f"{operation.index},{operation.operation} 操作参数错误")
            case 'write':
                if operateParam:
                    pyperclip.copy(operateParam)
                    self._input.hotkey('ctrl', 'v')
                else:
                    raise Exception(f"{operation.index},{operation.operation} 操作参数错误")
            case 'pic':
                operationWait, indexChangeFunc, operationWaitRandom = self.SearchPic(operation)
            case 'ocr':
                operationWait, indexChangeFunc, operationWaitRandom = self.Ocr(operation)
            case 'notify':
                notification_runtime.notify_operation(operateParam)
            case 'jmp':
                jmp = self.Jump(operateParam)
                if self._print_log:
                    log.debug(f'跳转 {operateParam}, 实际跳转到 {jmp}')
                return None, lambda x : jmp, None
            case 'script':
                operationWait, indexChangeFunc, operationWaitRandom = self._run_script(operation)
            case 'resource':
                raise Exception(f"{operation.index},{operation.operation} 只能在 _resource.csv 中使用")

        return operationWait, indexChangeFunc, operationWaitRandom

    def Jump(self, target:int|str):
        if target in self._jump_marks:
            return self._jump_marks[target]
        else:
            return target
