FROM python:3.11-slim

WORKDIR /app

# System deps for OpenCV / Tesseract / WeasyPrint (needed by later modules)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr libgl1 libglib2.0-0 libpango-1.0-0 libpangocairo-1.0-0 \
    libzbar0 libmagic1 build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
