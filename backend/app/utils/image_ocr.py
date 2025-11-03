# backend/app/utils/image_ocr.py

import cv2
import numpy as np
from PIL import Image
import pytesseract
import os
from dotenv import load_dotenv

# --- ADD THIS BLOCK ---
# Load environment variables from .env file
load_dotenv()
# Set the Tesseract command path if it's specified in the .env file
tess_cmd = os.getenv("TESSERACT_CMD")
if tess_cmd:
    pytesseract.pytesseract.tesseract_cmd = tess_cmd
# --- END OF BLOCK ---


def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
    # to OpenCV for basic cleanup
    arr = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    # light denoise + adaptive threshold
    gray = cv2.medianBlur(gray, 3)
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 11)
    # upscale a bit to help Tesseract
    bw = cv2.resize(bw, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    return Image.fromarray(bw)

def ocr_image_to_text(img_or_path) -> str:
    try:
        if isinstance(img_or_path, Image.Image):
            img = img_or_path
        else:
            img = Image.open(str(img_or_path))

        try:
            from PIL import ImageOps
            img = _preprocess_for_ocr(img)
        except Exception:
            pass

        try:
            # psm 6 = assume a block of text, OEM 3 = default LSTM
            return pytesseract.image_to_string(
                img, lang="sqi+eng", config="--psm 6 --oem 3"
            )
        except Exception:
            return pytesseract.image_to_string(img, lang="eng", config="--psm 6 --oem 3")
    except Exception:
        return ""