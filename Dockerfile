# Stage 1: build the React frontend
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python API that also serves the built frontend
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=8000
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY agent/ agent/
COPY api/ api/
COPY pipeline/ pipeline/
COPY schema_docs.yaml ./
COPY --from=web /web/dist frontend/dist
# Secrets (DATABASE_URL, GEMINI_API_KEY) are injected at runtime, never baked into the image.
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\",\"8000\")}/api/health')" || exit 1
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
