import pyautogui
import time
import csv

data_dict = {}

# 打开CSV文件
with open('config/test.csv', mode='r', encoding='utf-8') as csvfile:
    # 使用csv.DictReader读取CSV文件，它将每一行转换为一个字典
    reader = csv.DictReader(csvfile)
    # 遍历CSV文件中的每一行
    for row in reader:
        # 假设我们使用操作类型和操作的组合作为字典的键
        key = int(row['序号'])
        # 字典的值是剩下的两个字段
        value = {}
        value['type'] = int(row['操作类型'])
        value['operate'] = row['操作']
        if row['操作参数'] == "":
            value['operate_params'] = None
        else:
            value['operate_params'] = row['操作参数']
        if row['坐标范围'] == "":
            value['region'] = None
        else:
            region = row['坐标范围'].split(";")
            value['region'] = (int(region[0]),int(region[1]),int(region[2]),int(region[3]))
        if row['置信度'] == "":
            value['confidence'] = 0.8
        else:
            value['confidence'] = float(row['置信度'])
        if row['完成后等待'] == "":
            value['wait'] = None
        else:
            value['wait'] = float(row['完成后等待'])
        # 将键值对添加到字典中
        data_dict[key] = value

index = 1
while True:
    operate = data_dict[index]
    if operate['type'] == 1:
        try:
            center = pyautogui.locateCenterOnScreen(operate['operate_params'], confidence=operate['confidence'], region=operate['region'])
            if operate['operate'] == "click":
                pyautogui.click(center)
            elif operate['operate'] == "moveto":
                pyautogui.moveTo(center)
                pass
        except pyautogui.ImageNotFoundException:
            time.sleep(1)
        except Exception as e:
            raise e
        else:
            index += 1
            if operate['wait']:
                time.sleep(operate['wait'])
    elif operate['type'] == 2:
        try:
            if operate['operate'] == "down":
                if operate['operate_params']:
                    pyautogui.mouseDown(button=operate['operate_params'])
                else:
                    pyautogui.mouseDown()
            elif operate['operate'] == "up":
                if operate['operate_params']:
                    pyautogui.mouseUp(button=operate['operate_params'])
                else:
                    pyautogui.mouseUp()
            elif operate['operate'] == "click":
                if operate['operate_params']:
                    pyautogui.click(button=operate['operate_params'])
                else:
                    pyautogui.click()
            elif operate['operate'] == "move":
                if operate['operate_params']:
                    offset = operate['operate_params'].split(";")
                    pyautogui.moveRel(xOffset=float(offset[0]), yOffset=float(offset[1]))
                else:
                    raise Exception("操作参数错误")
        except Exception as e:
            raise e
        else:
            index += 1
            if operate['wait']:
                time.sleep(operate['wait'])
    elif operate['type'] == 3:
        pass

    if index > len(data_dict):
        break