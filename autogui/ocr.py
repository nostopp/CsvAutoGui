import threading
import pyautogui
import cv2
import numpy as np
import time
from .baseInput import BaseInput

SAVE_OCR_FILE = False
OCR_FILE_PATH = None

COMPARE_START = ('<;', '<=;', '>;', '>=;', '==;', '!=;')

class LazyPaddleOCR:
    _instance = None
    _importLock = threading.Lock()
    _imported = False
    
    def __init__(self):
        self._ocrEngine = None
        # self._drawOcr = None
        self._startedInit = False
        self._initThread = threading.Thread(target=self.initialize)
        self._initThread.daemon = True
        self._initThread.start()

    @classmethod
    def Instance(cls):
        if cls._instance is None:
            if cls._instance is None:
                cls._instance = LazyPaddleOCR()
        return cls._instance
    
    @classmethod
    def _importPaddleocr(cls):
        with cls._importLock:
            if not cls._imported:
                # print("LazyPaddleOCR: Importing PaddleOCR...")
                global PaddleOCR#, draw_ocr
                from paddleocr import PaddleOCR#, draw_ocr  
                cls._imported = True
                # print("LazyPaddleOCR: PaddleOCR imported successfully.")
    
    def initialize(self):
        if not self._startedInit:
            # print("LazyPaddleOCR: Initializing OCR engine...")
            self._startedInit = True
            if not LazyPaddleOCR._imported:
                LazyPaddleOCR._importPaddleocr()  # 触发导入
            self._ocrEngine = PaddleOCR(
                # lang='ch',
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_detection_model_dir='ocr_model/det', 
                text_recognition_model_name='PP-OCRv5_mobile_rec',
                text_recognition_model_dir='ocr_model/rec',
                use_textline_orientation=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
            )
            # self._drawOcr = draw_ocr
            print("OCR初始化完成")
    
    def getOcr(self):
        if not self._startedInit:
            self.initialize()  # 如果未初始化则启动
        if self._initThread and self._initThread.is_alive():
            # print("LazyPaddleOCR: Waiting for OCR engine to be ready...")
            self._initThread.join()
        return self._ocrEngine
        
    # def drawOcr(self, image, boxes, texts=None, scores=None):
    #     if not self._startedInit:
    #         self.initialize()  # 如果未初始化则启动
    #     if self._initThread and self._initThread.is_alive():
    #         self._initThread.join()
    #     return self._drawOcr(image, boxes, texts, scores)
_lazyOcr = LazyPaddleOCR.Instance()

def SaveOCRFile(ocrResult, cvImg):
    if ocrResult is None or not ocrResult or cvImg is None:
        return

    # image = cv2.cvtColor(cvImg, cv2.COLOR_BGR2RGB)  # 转换为RGB格式

    # result = ocrResult[0]  # 获取第一页结果
    # boxes = result['rec_polys']  # 文本框坐标列表
    # texts = result['rec_texts']  # 识别的文本列表
    # scores = result['rec_scores']  # 置信度列表
    
    # visualized_image = _lazyOcr.drawOcr(image, boxes, texts, scores)

    # cv2.imwrite(f'{OCR_FILE_PATH}/OCR-{time.strftime("%m%d%H%M%S", time.localtime())}.png', cv2.cvtColor(visualized_image, cv2.COLOR_RGB2BGR))
    result = ocrResult[0]
    result.save_to_img(f'{OCR_FILE_PATH}/OCR-{time.strftime("%m%d%H%M%S", time.localtime())}.png')

def GetTargetCenter(points, findStr, word):
    wordBox = np.array(points)  # 文本框四个点坐标
                
    # 计算目标词在文本中的位置比例
    wordIdx = word.find(findStr)
    wordLen = len(findStr)
    totalLen = len(word)
    
    midRatio = (2 * wordIdx + wordLen) / totalLen / 2
    midPoint = wordBox[0] + (wordBox[1]-wordBox[0]) * midRatio
    midPoint += (wordBox[3] - wordBox[0]) / 2
    height = int(np.linalg.norm(wordBox[3] - wordBox[0]))
    width = int(wordLen / totalLen * np.linalg.norm(wordBox[1] - wordBox[0]))
    return int(midPoint[0]), int(midPoint[1]), width, height

def FindTextInResult(ocrResult, findStr : str, confidence: float):
    if ocrResult is None or not ocrResult:
        return None, None, None, None

    result = ocrResult[0]  # 获取第一页结果
    texts = result['rec_texts']  # 识别的文本列表
    scores = result['rec_scores']  # 置信度列表
    boxes = result['rec_polys']  # 文本框坐标列表
    
    for i, (text, score) in enumerate(zip(texts, scores)):
        if findStr in text and score >= confidence:
            return GetTargetCenter(boxes[i], findStr, text)
    
    return None, None, None, None

def CompareNumInResult(ocrResult, findStr: str, confidence: float, compare):
    if ocrResult is None or not ocrResult:
        return None, None, None, None

    compareFunc = None
    match compare:
        case '<':
            compareFunc = lambda a, b: a < b
        case '<=':
            compareFunc = lambda a, b: a <= b
        case '>':
            compareFunc = lambda a, b: a > b
        case '>=':
            compareFunc = lambda a, b: a >= b
        case '==':
            compareFunc = lambda a, b: a == b
        case '!=':
            compareFunc = lambda a, b: a != b

    result = ocrResult[0]  # 获取第一页结果
    texts = result['rec_texts']  # 识别的文本列表
    scores = result['rec_scores']  # 置信度列表
    boxes = result['rec_polys']  # 文本框坐标列表
    
    for i, (text, score) in enumerate(zip(texts, scores)):
        if text.isdigit() and score >= confidence and compareFunc(float(text), float(findStr)):
            wordBox = np.array(boxes[i])
            midPoint = wordBox[0] + (wordBox[1]-wordBox[0]) * 0.5
            midPoint += (wordBox[3] - wordBox[0]) / 2
            height = int(np.linalg.norm(wordBox[3] - wordBox[0]))
            width = int(np.linalg.norm(wordBox[1] - wordBox[0]))
            return midPoint[0], midPoint[1], width, height

    return None, None, None, None

def OCR(findStr:str, input:BaseInput, findRegion=None, confidence:float = 0.8) -> bool:
    if findStr is None:
        return
    # screenshotIm = pyautogui.screenshot()
    # cvImg = np.array(screenshotIm.convert('RGB'))
    screenshotIm = input.screenShot()
    # cvImg = cv2.cvtColor(screenshotIm, cv2.COLOR_BGR2GRAY)
    cvImg = screenshotIm
    if findRegion and len(findRegion) == 4:
        findRegion = input.convertFindRegion(findRegion)
        cvImg = cvImg[findRegion[1]:findRegion[1] + findRegion[3], findRegion[0]:findRegion[0] + findRegion[2]]
    result = _lazyOcr.getOcr().predict(cvImg)

    if findStr.startswith(COMPARE_START):
        split = findStr.split(';')
        compare = split[0]
        targetStr = split[1]
        xCenter, yCenter, width, height = CompareNumInResult(result, targetStr, confidence, compare)
    else:
        xCenter, yCenter, width, height = FindTextInResult(result, findStr, confidence)

    if xCenter and yCenter and findRegion and len(findRegion) == 4:
        xCenter += findRegion[0]
        yCenter += findRegion[1]

    if SAVE_OCR_FILE:
        SaveOCRFile(result, cvImg)

    try:
        screenshotIm.fp.close()
    except AttributeError:
        pass

    return xCenter, yCenter, width, height