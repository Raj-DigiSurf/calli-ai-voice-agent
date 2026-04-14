# Microsoft's official Playwright image — Chromium pre-installed, no build-time download
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

# Install Python dependencies
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code and dashboard
COPY server/ ./server/
COPY dashboard/ ./dashboard/

# Playwright browsers are already in the base image
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

EXPOSE 8000

CMD cd server && uvicorn main:app --host 0.0.0.0 --port $PORT
