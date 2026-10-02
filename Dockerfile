FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.lock.txt backend/requirements.lock.txt
RUN pip install --no-cache-dir -r backend/requirements.lock.txt
COPY backend/ backend/
COPY data/examples/public_demo.csv data/examples/public_demo.csv
COPY data/examples/public_demo.json data/examples/public_demo.json
COPY --from=frontend /build/dist frontend/dist/
RUN useradd --create-home --uid 10001 slab && mkdir -p /app/runtime-public && chown -R slab:slab /app/runtime-public
USER slab
ENV SLAB_MODE=public SLAB_DATA_DIR=/app/runtime-public
EXPOSE 8765
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8765"]
