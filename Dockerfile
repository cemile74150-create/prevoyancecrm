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
    fonts-liberation \
    fonts-crosextra-carlito \
    libreoffice-writer-nogui \
    && rm -rf /var/lib/apt/lists/* \
    && (test -d /usr/share/tesseract-ocr/5/tessdata && echo export TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata > /etc/profile.d/tessdata.sh || true)
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata
# Fallbacks used by app if path differs by distro
ENV OCR_TESSDATA_CANDIDATES=/usr/share/tesseract-ocr/5/tessdata:/usr/share/tesseract-ocr/4.00/tessdata:/usr/share/tessdata
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
# Node 20 from the frontend stage: the analysis engine runs under FastAPI via tsx.
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend-build /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
# Bust cache when templates change (Railway / BuildKit)
ARG TEMPLATE_CACHEBUST=mg_lsa_v2_20260826
RUN echo "templates=$TEMPLATE_CACHEBUST"
COPY backend/ ./backend/
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN cd /app/backend/analyse_prevoyance_engine \
    && npm ci --omit=dev \
    && npx playwright install --with-deps chromium
COPY --from=frontend-build /app/frontend/build ./frontend/build
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % (__import__('os').environ.get('PORT') or '8000'), timeout=3)" || exit 1
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
