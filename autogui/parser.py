import csv
import os
from pathlib import Path
from .scaleHelper import ScaleHelper
from csv_schema import (
    COL_CONFIDENCE,
    COL_DISABLE_GRAYSCALE,
    COL_INDEX,
    COL_JUMP_MARK,
    COL_MOVE_TIME,
    COL_OPERATION,
    COL_PARAM,
    COL_RANGE_RANDOM,
    COL_REGION,
    COL_RETRY,
    COL_SEARCH_TARGET,
    COL_WAIT,
)

csvDataDict = {}

def CheckValueInCsv(row : dict, key : str) -> bool:
    return key in row and row[key] != None and len(row[key]) > 0

def GetCsv(path:str, scaleHelper:ScaleHelper, fileName:str = "main.csv") -> dict:
    cache_key = os.fspath(Path(path) / fileName)
    if cache_key in csvDataDict:
        return csvDataDict[cache_key]

    csvDataDict[cache_key] = ParseCsv(path, fileName, scaleHelper)
    return csvDataDict[cache_key]

def ParseParamData(param:str, operate:str, scaleHelper:ScaleHelper):
    param_data = None
    match operate:
        case 'click' | 'mDown' | 'mUp' | 'press' | 'kDown' | 'kUp' | 'write' | 'notify':
            param_data = param
        case 'jmp':
            param_data = param
            try:
                param_data = int(param_data)
            except:
                pass

        case 'pic' | 'ocr':
            param_data = param.split(";")
            if len(param_data) == 3:
                try:
                    param_data[1] = int(param_data[1])
                except:
                    pass
                try:
                    param_data[2] = int(param_data[2])
                except:
                    pass

            param_data = tuple(param_data)
        case 'mMove' | 'mMoveTo':
            data = param.split(";")
            xOffset=scaleHelper.getScaleInt(int(data[0])) 
            yOffset=scaleHelper.getScaleInt(int(data[1]))
            param_data = (xOffset, yOffset)

    return param_data

def ParseCsv(path:str, fileName:str, scaleHelper:ScaleHelper) -> dict:
    dataDict = dict()
    csv_path = Path(path) / fileName
    with open(csv_path, mode='r', encoding='utf-8') as csvfile:
        # 使用csv.DictReader读取CSV文件，它将每一行转换为一个字典
        reader = csv.DictReader(csvfile)
        # 遍历CSV文件中的每一行
        for row in reader:
            key = int(row[COL_INDEX])
            value = {}
            value['index'] = key
            value['operate'] = row[COL_OPERATION]
            if CheckValueInCsv(row, COL_PARAM):
                value['operate_param'] = ParseParamData(row[COL_PARAM], value['operate'], scaleHelper)
            if CheckValueInCsv(row, COL_SEARCH_TARGET):
                value['search_pic'] = row[COL_SEARCH_TARGET]
            if CheckValueInCsv(row, COL_REGION):
                region = row[COL_REGION].split(";")
                region = scaleHelper.getScaleRegion((int(region[0]),int(region[1]),int(region[2]),int(region[3])))
                value['pic_region'] = region
            if CheckValueInCsv(row, COL_CONFIDENCE):
                value['confidence'] = float(row[COL_CONFIDENCE])
            if CheckValueInCsv(row, COL_DISABLE_GRAYSCALE):
                if int(row[COL_DISABLE_GRAYSCALE]) == 1:
                    value['disable_grayscale'] = True
            if CheckValueInCsv(row, COL_WAIT):
                if ';' in row[COL_WAIT]:
                    param = str.split(row[COL_WAIT], ';')
                    value['wait'] = float(param[0])
                    value['wait_random'] = float(param[1])
                else:
                    value['wait'] = float(row[COL_WAIT])
            if CheckValueInCsv(row, COL_RETRY):
                if ';' in row[COL_RETRY]:
                    param = str.split(row[COL_RETRY], ';')
                    value['pic_retry_time'] = float(param[0])
                    value['pic_retry_time_random'] = float(param[1])
                else:
                    value['pic_retry_time'] = float(row[COL_RETRY])
            if CheckValueInCsv(row, COL_RANGE_RANDOM):
                if int(row[COL_RANGE_RANDOM]) == 1:
                    value['pic_range_random'] = True
            if CheckValueInCsv(row, COL_MOVE_TIME):
                value['move_time'] = float(row[COL_MOVE_TIME])
            if CheckValueInCsv(row, COL_JUMP_MARK):
                value['jump_mark'] = row[COL_JUMP_MARK]
            # 将键值对添加到字典中
            dataDict[key] = value
        return dataDict
