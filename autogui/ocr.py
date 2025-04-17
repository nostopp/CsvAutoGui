from paddleocr import PaddleOCR, draw_ocr
import pyautogui
import cv2
import numpy as np
import time

SAVE_OCR_FILE = False

ocr = PaddleOCR(use_angle_cls=True, lang='ch')

def SaveOCRFile(ocrResult, cvImg):
    if ocrResult is None or cvImg is None:
        return

    image = cv2.cvtColor(cvImg, cv2.COLOR_GRAY2RGB)  # 转换为RGB格式

    boxes = [detec[0] for line in ocrResult for detec in line]
    texts = [detec[1][0] for line in ocrResult for detec in line]
    scores = [detec[1][1] for line in ocrResult for detec in line]
    visualized_image = draw_ocr(
        image, 
        boxes, 
        texts, 
        scores, 
    )

    cv2.imwrite(f'OCR-{time.strftime("%m%d%H%M%S", time.localtime())}.jpg', cv2.cvtColor(visualized_image, cv2.COLOR_RGB2BGR))

def FindTextInResult(ocrResult, findStr : str, confidence: float):
    if ocrResult is None:
        return None, None

    for line in ocrResult:
        for word_info in line:
            word, conf = word_info[1]
            if findStr in word and conf >= confidence:
                points = word_info[0]
                xCenter = int(sum(p[0] for p in points) / 4)
                yCenter = int(sum(p[1] for p in points) / 4)
                return xCenter, yCenter
    
    return None, None
    
def OCR(findStr:str, findRegion=None, confidence:float = 0.8) -> bool:
    if findStr is None:
        return
    screenshotIm = pyautogui.screenshot()
    cvImg = np.array(screenshotIm.convert('RGB'))
    cvImg = cvImg[:, :, ::-1].copy()  # -1 does RGB -> BGR
    cvImg = cv2.cvtColor(cvImg, cv2.COLOR_BGR2GRAY)
    if findRegion and len(findRegion) == 4:
        cvImg = cvImg[findRegion[1]:findRegion[1] + findRegion[3], findRegion[0]:findRegion[0] + findRegion[2]]
    result = ocr.ocr(cvImg, cls=True)

    xCenter, yCenter = FindTextInResult(result, findStr, confidence)

    if SAVE_OCR_FILE:
        SaveOCRFile(result, cvImg)

    try:
        screenshotIm.fp.close()
    except AttributeError:
        pass

    return xCenter, yCenter