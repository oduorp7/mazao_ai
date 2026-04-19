# Use a slim Python 3.12 image for a fast, predictable build
FROM python:3.12-slim

# Set environment variables for non-interactive installs and unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (required for lxml and other C-extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    libz-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project context
COPY . .

# Ensure apps/ and apps/agent are in the PYTHONPATH (matching local dev)
ENV PYTHONPATH="/app:/app/apps:/app/apps/agent"

# Start the Telegram Bot worker
# We use 'python' because we aren't using a web server (polling mode)
CMD ["python", "apps/telegram/bot.py"]
