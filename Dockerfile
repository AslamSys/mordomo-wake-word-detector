FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download built-in OWW models at build time so container starts fast
RUN python -c "import openwakeword; openwakeword.utils.download_models()"

COPY src/ src/

# models/ volume — mount custom ONNX model here at runtime
VOLUME ["/app/models"]

CMD ["python", "-m", "src.main"]
