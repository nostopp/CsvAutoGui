import cv2

class ScaleHelper:
    _instance = None

    @classmethod
    def Instance(cls):
        if cls._instance is None:
            cls._instance = ScaleHelper()
        return cls._instance

    def Init(self, scale, offset, scale_image):
        self.scale = scale
        self.offset = offset
        self.scale_image = scale_image
        self.need_scale = False
        self.need_offset = False

        if scale != 1.0:
            self.need_scale = True

        if offset:
            offset = offset.split(";")
            if len(offset) == 2:
                x = int(offset[0])
                y = int(offset[1])
                if x != 0 or y != 0:
                    self.need_offset = True
                self.offset = (x, y)
            else:
                raise Exception("偏移值格式错误")

    def getScalePos(self, pos):
        if not self.need_scale and not self.need_offset:
            return pos

        if pos is None:
            return None
        if isinstance(pos, tuple):
            x, y = pos
            x = int(x * self.scale) + self.offset[0]
            y = int(y * self.scale) + self.offset[1]
            return (x, y)
        else:
            raise Exception("坐标格式错误")

    def getScaleRegion(self, region):
        if not self.need_scale and not self.need_offset:
            return region

        if region is None:
            return None
        if isinstance(region, tuple):
            x, y, w, h = region
            x = int(x * self.scale) + self.offset[0]
            y = int(y * self.scale) + self.offset[1]
            w = int(w * self.scale)
            h = int(h * self.scale)
            return (x, y, w, h)
        else:
            raise Exception("区域格式错误")

    def getScaleInt(self, value):
        if not self.need_scale:
            return value

        if value is None:
            return None
        if isinstance(value, int) or isinstance(value, float):
            return int(value * self.scale)
        else:
            raise Exception("整数格式错误")

    def getScaleImg(self, imgPath):
        img = cv2.imread(imgPath, cv2.IMREAD_COLOR)

        if not self.scale_image or not self.need_scale:
            return img
        img = cv2.resize(img, (
            int(img.shape[1] * self.scale),
            int(img.shape[0] * self.scale)
        ), interpolation=cv2.INTER_CUBIC)

        return img