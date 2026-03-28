FROM python:3.11-slim

# Install LibreOffice and Fonts for PDF conversion on Linux
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-core \
    libreoffice-writer \
    default-jre \
    fonts-liberation \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Start the FastAPI server using Uvicorn
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
