# Build React frontend
FROM node:20-bookworm AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/yarn.lock ./
RUN yarn install --frozen-lockfile || yarn install
COPY frontend/ ./
ENV CI=true
RUN yarn build

# Runtime: FastAPI serves API + static frontend
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-deu \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && (test -d /usr/share/tesseract-ocr/5/tessdata && echo export TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata > /etc/profile.d/tessdata.sh || true)
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata
# Fallbacks used by app if path differs by distro
ENV OCR_TESSDATA_CANDIDATES=/usr/share/tesseract-ocr/5/tessdata:/usr/share/tesseract-ocr/4.00/tessdata:/usr/share/tessdata
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/build ./frontend/build
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
