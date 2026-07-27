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
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/build ./frontend/build
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
