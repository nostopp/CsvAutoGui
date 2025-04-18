# from paddleocr import PaddleOCR, draw_ocr
import threading
import pyautogui
import cv2
import numpy as np
import time

SAVE_OCR_FILE = False
OCR_FILE_PATH = None

class LazyPaddleOCR:
    _instance = None
    _importLock = threading.Lock()
    _imported = False
    
    def __init__(self):
        self._ocrEngine = None
        self._drawOcr = None
        self._startedInit = False
        self._initThread = threading.Thread(target=self.initialize)
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
                global PaddleOCR, draw_ocr
                from paddleocr import PaddleOCR, draw_ocr  
                cls._imported = True
                # print("LazyPaddleOCR: PaddleOCR imported successfully.")
    
    def initialize(self):
        if not self._startedInit:
            # print("LazyPaddleOCR: Initializing OCR engine...")
            self._startedInit = True
            if not LazyPaddleOCR._imported:
                LazyPaddleOCR._importPaddleocr()  # 触发导入
            self._ocrEngine = PaddleOCR(
                use_angle_cls=True, lang='ch', show_log=False,
                det_model_dir='ocr_model/det', 
                rec_model_dir='ocr_model/rec',
                cls_model_dir='ocr_model/cls'
            )
            self._drawOcr = draw_ocr
            # print("LazyPaddleOCR: OCR engine initialized successfully.")
    
    def getOcr(self):
        if not self._startedInit:
            self.initialize()  # 如果未初始化则启动
        if self._initThread and self._initThread.is_alive():
            # print("LazyPaddleOCR: Waiting for OCR engine to be ready...")
            self._initThread.join()
        return self._ocrEngine
        
    def drawOcr(self, image, boxes, texts=None, scores=None):
        if not self._startedInit:
            self.initialize()  # 如果未初始化则启动
        if self._initThread and self._initThread.is_alive():
            self._initThread.join()
        return self._drawOcr(image, boxes, texts, scores)
_lazyOcr = LazyPaddleOCR.Instance()

def SaveOCRFile(ocrResult, cvImg):
    if ocrResult is None or cvImg is None:
        return

    image = cv2.cvtColor(cvImg, cv2.COLOR_GRAY2RGB)  # 转换为RGB格式

    boxes = [detec[0] for line in ocrResult for detec in line or {}]
    texts = [detec[1][0] for line in ocrResult for detec in line or {}]
    scores = [detec[1][1] for line in ocrResult for detec in line or {}]
    visualized_image = _lazyOcr.drawOcr(image, boxes, texts, scores)

    cv2.imwrite(f'{OCR_FILE_PATH}/OCR-{time.strftime("%m%d%H%M%S", time.localtime())}.jpg', cv2.cvtColor(visualized_image, cv2.COLOR_RGB2BGR))

def GetTargetCenter(points, findStr, word):
    wordBox = np.array(points)  # 文本框四个点坐标
                
    # 计算目标词在文本中的位置比例
    wordIdx = word.find(findStr)
    wordLen = len(findStr)
    totalLen = len(word)
    
    midRatio = (2 * wordIdx + wordLen) / totalLen / 2
    midPoint = wordBox[0] + (wordBox[1]-wordBox[0]) * midRatio
    midPoint += (wordBox[3] - wordBox[0]) / 2
    return int(midPoint[0]), int(midPoint[1])

def FindTextInResult(ocrResult, findStr : str, confidence: float):
    if ocrResult is None:
        return None, None

    for line in ocrResult:
        for word_info in line or []:
            word, conf = word_info[1]
            if findStr in word and conf >= confidence:
                points = word_info[0]
                return GetTargetCenter(points, findStr, word)
    
    return None, None
    
def OCR(findStr:str, findRegion=None, confidence:float = 0.8) -> bool:
    if findStr is None:
        return
    screenshotIm = pyautogui.screenshot()
    cvImg = np.array(screenshotIm.convert('RGB'))
    cvImg = cv2.cvtColor(cvImg, cv2.COLOR_RGB2GRAY)
    if findRegion and len(findRegion) == 4:
        cvImg = cvImg[findRegion[1]:findRegion[1] + findRegion[3], findRegion[0]:findRegion[0] + findRegion[2]]
    result = _lazyOcr.getOcr().ocr(cvImg, cls=True)

    xCenter, yCenter = FindTextInResult(result, findStr, confidence)
    if xCenter and yCenter and findRegion and len(findRegion) == 4:
        xCenter += findRegion[0]
        yCenter += findRegion[1]

    if SAVE_OCR_FILE:
        SaveOCRFile(result, cvImg)

    try:
        screenshotIm.fp.close()
    except AttributeError:
        pass

    return xCenter, yCenter