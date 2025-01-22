import csv

def CheckValueInCsv(row : dict, key : str) -> bool:
    return key in row and row[key] != None and len(row[key]) > 0

def ParseCsv(path:str) -> dict:
    dataDict = dict()
    with open(f'{path}/config.csv', mode='r', encoding='utf-8') as csvfile:
        # 使用csv.DictReader读取CSV文件，它将每一行转换为一个字典
        reader = csv.DictReader(csvfile)
        # 遍历CSV文件中的每一行
        for row in reader:
            key = int(row['序号'])
            value = {}
            value['index'] = key
            value['operate'] = row['操作']
            if CheckValueInCsv(row, '操作参数'):
                value['operate_param'] = row['操作参数']
            if CheckValueInCsv(row, '图片名称'):
                value['search_pic'] = row['图片名称']
            if CheckValueInCsv(row, '图片坐标范围'):
                region = row['图片坐标范围'].split(";")
                value['pic_region'] = (int(region[0]),int(region[1]),int(region[2]),int(region[3]))
            if CheckValueInCsv(row, '图片置信度'):
                value['confidence'] = float(row['图片置信度'])
            if CheckValueInCsv(row, '完成后等待时间'):
                value['wait'] = float(row['完成后等待时间'])
            if CheckValueInCsv(row, '未找到图片重试时间'):
                value['pic_retry_time'] = float(row['未找到图片重试时间'])
            # 将键值对添加到字典中
            dataDict[key] = value
        return dataDict