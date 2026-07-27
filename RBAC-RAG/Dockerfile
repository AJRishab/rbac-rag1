# Hugging Face Spaces (Docker) — serves React UI + FastAPI on port 7860
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --legacy-peer-deps
COPY frontend/ .
# Same-origin API on the Space URL → empty backend URL → requests go to /api
ENV REACT_APP_BACKEND_URL=
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-space.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/build ./frontend_build

ENV FRONTEND_BUILD_DIR=/app/frontend_build
ENV PYTHONUNBUFFERED=1

WORKDIR /app/backend
EXPOSE 7860
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
