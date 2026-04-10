from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from autogui import ocr as runtime_ocr

class RuntimeOcrPreviewAdapter:
    """Thin adapter for editor-side OCR preview reuse."""

    def preview_from_path(self, image_path: Path) -> list[str]:
        if not image_path.exists():
            return []
        image = Image.open(image_path)
        return self.preview_from_image(image)

    def preview_from_image(self, image: Image.Image) -> list[str]:
        rgb_image = image.convert("RGB")
        cv_img = cv2.cvtColor(np.array(rgb_image), cv2.COLOR_RGB2BGR)
        try:
            result = runtime_ocr._lazyOcr.getOcr().predict(cv_img)
        except Exception:
            return []

        if not result:
            return []

        page = result[0]
        texts = page.get("rec_texts", [])
        return [str(text).strip() for text in texts if str(text).strip()]
