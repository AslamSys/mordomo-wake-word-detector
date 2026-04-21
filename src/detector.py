"""
OpenWakeWord wrapper.

Handles:
- Loading custom ONNX model or built-in model
- Buffering 30ms VAD frames into 80ms chunks (1280 samples)
- Running inference and returning confidence scores
"""
import logging
import os
from collections import deque
from typing import Optional

import numpy as np

logger = logging.getLogger("wake-word-detector.detector")


class WakeWordDetector:
    def __init__(self, model_path: str, wake_word: str, threshold: float, sample_rate: int = 16000):
        self._wake_word = wake_word
        self._threshold = threshold
        self._sample_rate = sample_rate
        self._model = None
        self._model_key: Optional[str] = None
        self._buffer = np.array([], dtype=np.int16)
        self._oww_chunk = 1280  # samples OpenWakeWord processes at once

        self._load_model(model_path)

    def _load_model(self, model_path: str):
        import openwakeword
        from openwakeword.model import Model

        if model_path and os.path.isfile(model_path):
            logger.info(f"Loading custom wake word model: {model_path}")
            self._model = Model(wakeword_models=[model_path], inference_framework="onnx")
            # Key in predictions dict is the model filename without extension
            self._model_key = os.path.splitext(os.path.basename(model_path))[0]
        else:
            target_word = self._wake_word or "alexa"
            if model_path:
                logger.warning(f"Model file not found: {model_path} — falling back to built-in '{target_word}'")
            else:
                logger.info(f"No custom model configured — using built-in '{target_word}'")
            
            try:
                self._model = Model(wakeword_models=[target_word], inference_framework="onnx")
                self._model_key = target_word
            except Exception as e:
                logger.error(f"Failed to load built-in model '{target_word}': {e}. Falling back to 'alexa'")
                self._model = Model(wakeword_models=["alexa"], inference_framework="onnx")
                self._model_key = "alexa"

        logger.info(f"Wake word detector ready (key={self._model_key}, threshold={self._threshold})")

    def process_frame(self, pcm_bytes: bytes) -> Optional[float]:
        """
        Feed a PCM frame (any size). Returns confidence score if wake word
        is detected above threshold, else None.
        """
        frame = np.frombuffer(pcm_bytes, dtype=np.int16)
        self._buffer = np.concatenate([self._buffer, frame])

        # Process as many full OWW chunks as available
        confidence = None
        while len(self._buffer) >= self._oww_chunk:
            chunk = self._buffer[: self._oww_chunk]
            self._buffer = self._buffer[self._oww_chunk :]

            prediction = self._model.predict(chunk)
            score = prediction.get(self._model_key, 0.0)

            if score >= self._threshold:
                confidence = float(score)
                # Reset internal model state after detection to avoid double-fire
                self._model.reset()
                self._buffer = np.array([], dtype=np.int16)
                break

        return confidence
