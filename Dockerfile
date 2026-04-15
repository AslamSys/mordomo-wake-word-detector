FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Install openwakeword without tflite-runtime (not available on ARM64/Python 3.12)
# We use ONNX inference only, so tflite is not needed
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps openwakeword==0.6.0

# Download built-in OWW models at build time so container starts fast
RUN python -c "import openwakeword; openwakeword.utils.download_models()"

COPY src/ src/

# models/ volume — mount custom ONNX model here at runtime
VOLUME ["/app/models"]

CMD ["python", "-m", "src.main"]
