FROM python:3.11-slim

# System deps for Remotion (Node + ffmpeg) and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    ffmpeg \
    chromium \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Node deps for Remotion
COPY remotion/package*.json ./remotion/
RUN cd remotion && npm install --legacy-peer-deps

# App source
COPY . .

# Writable runtime directories
RUN mkdir -p data logs downloads remotion/public

EXPOSE 8080

CMD ["python", "main.py", "start"]
