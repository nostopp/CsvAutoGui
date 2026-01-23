import csv
from .scaleHelper import ScaleHelper

csvDataDict = {}

def CheckValueInCsv(row : dict, key : str) -> bool:
    return key in row and row[key] != None and len(row[key]) > 0

def GetCsv(path:str, scaleHelper:ScaleHelper, fileName:str = "main.csv") -> dict:
    if fileName in csvDataDict:
        return csvDataDict[fileName]

    csvDataDict[fileName] = ParseCsv(path, fileName, scaleHelper)
    return csvDataDict[fileName]

def ParseParamData(param:str, operate:str, scaleHelper:ScaleHelper):
    param_data = None
    match operate:
        case 'click' | 'mDown' | 'mUp' | 'press' | 'kDown' | 'kUp' | 'write':
            param_data = param
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
    with open(f'{path}/{fileName}', mode='r', encoding='utf-8') as csvfile:
        # 使用csv.DictReader读取CSV文件，它将每一行转换为一个字典
        reader = csv.DictReader(csvfile)
        # 遍历CSV文件中的每一行
        for row in reader:
            key = int(row['序号'])
            value = {}
            value['index'] = key
            value['operate'] = row['操作']
            if CheckValueInCsv(row, '操作参数'):
                value['operate_param'] = ParseParamData(row['操作参数'], value['operate'], scaleHelper)
            if CheckValueInCsv(row, '图片/ocr名称'):
                value['search_pic'] = row['图片/ocr名称']
            if CheckValueInCsv(row, '图片/ocr坐标范围'):
                region = row['图片/ocr坐标范围'].split(";")
                region = scaleHelper.getScaleRegion((int(region[0]),int(region[1]),int(region[2]),int(region[3])))
                value['pic_region'] = region
            if CheckValueInCsv(row, '图片/ocr置信度'):
                value['confidence'] = float(row['图片/ocr置信度'])
            if CheckValueInCsv(row, '完成后等待时间'):
                if ';' in row['完成后等待时间']:
                    param = str.split(row['完成后等待时间'], ';')
                    value['wait'] = float(param[0])
                    value['wait_random'] = float(param[1])
                else:
                    value['wait'] = float(row['完成后等待时间'])
            if CheckValueInCsv(row, '未找到图片/ocr重试时间'):
                if ';' in row['未找到图片/ocr重试时间']:
                    param = str.split(row['未找到图片/ocr重试时间'], ';')
                    value['pic_retry_time'] = float(param[0])
                    value['pic_retry_time_random'] = float(param[1])
                else:
                    value['pic_retry_time'] = float(row['未找到图片/ocr重试时间'])
            if CheckValueInCsv(row, '图片/ocr定位移动随机'):
                if int(row['图片/ocr定位移动随机']) == 1:
                    value['pic_range_random'] = True
            if CheckValueInCsv(row, '移动操作用时'):
                value['move_time'] = float(row['移动操作用时'])
            if CheckValueInCsv(row, '跳转标记'):
                value['jump_mark'] = row['跳转标记']
            # 将键值对添加到字典中
            dataDict[key] = value
        return dataDict