import cv2
import pyautogui
from pyautogui import Point


class LocateImageNotFoundException(pyautogui.ImageNotFoundException):
    def __init__(self, confidence_score: float):
        super().__init__(f'Could not locate the image (highest confidence = {confidence_score:.3f})')
        self.confidence_score = confidence_score


def locateCenterColorSensitiveOnImage(needleImage, haystackImage, confidence: float = 0.999, region=None):
    needleHeight, needleWidth = needleImage.shape[:2]

    if region:
        offsetX, offsetY, regionWidth, regionHeight = region
        haystackImage = haystackImage[offsetY : offsetY + regionHeight, offsetX : offsetX + regionWidth]
    else:
        offsetX, offsetY = 0, 0

    if haystackImage.shape[0] < needleHeight or haystackImage.shape[1] < needleWidth:
        raise ValueError('needle dimension(s) exceed the haystack image or region dimensions')

    result = cv2.matchTemplate(haystackImage, needleImage, cv2.TM_SQDIFF_NORMED)
    minVal, _, minLoc, _ = cv2.minMaxLoc(result)
    confidenceScore = max(0.0, 1.0 - float(minVal))

    if confidenceScore < float(confidence):
        raise LocateImageNotFoundException(confidenceScore)

    centerX = minLoc[0] + offsetX + needleWidth // 2
    centerY = minLoc[1] + offsetY + needleHeight // 2
    return Point(centerX, centerY), confidenceScore
