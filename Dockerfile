FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json frontend/tsconfig.json /app/frontend/
RUN npm ci
COPY frontend/src/ /app/frontend/src/
RUN npm run build

FROM python:3.11-slim AS tester
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ /app/app/
COPY tests/ /app/tests/
RUN pip install pytest pytest-asyncio httpx && pytest tests/ -v

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ /app/app/
COPY frontend/ /app/frontend/
COPY --from=frontend-builder /app/frontend/dist/ /app/frontend/dist/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
