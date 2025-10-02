FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

ENV DEBIAN_FRONTEND=noninteractive TZ=Europe/Belgrade
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      tzdata \
      tesseract-ocr \
      tesseract-ocr-sqi \
      poppler-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
# add OCR python libs here so you don't have to touch requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt pdf2image pytesseract

COPY ./app /app/app
ENV PYTHONUNBUFFERED=1
