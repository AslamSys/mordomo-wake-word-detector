import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # ZeroMQ — subscribe to VAD audio stream
    zmq_vad_url: str = field(default_factory=lambda: os.getenv("ZMQ_VAD_URL", "tcp://audio-capture-vad:5555"))
    zmq_topic: str = field(default_factory=lambda: os.getenv("ZMQ_TOPIC", "audio.raw"))

    # OpenWakeWord model — custom ASLAM model if present, else built-in "alexa" for testing
    model_path: str = field(default_factory=lambda: os.getenv("WAKE_WORD_MODEL_PATH", ""))
    wake_word: str = field(default_factory=lambda: os.getenv("WAKE_WORD", "aslam"))
    threshold: float = field(default_factory=lambda: float(os.getenv("WAKE_WORD_THRESHOLD", "0.5")))

    # Audio
    sample_rate: int = 16000
    oww_chunk_size: int = 1280  # 80ms @ 16kHz — OpenWakeWord internal chunk

    # NATS
    nats_url: str = field(default_factory=lambda: os.getenv("NATS_URL", "nats://nats:4222"))

    # Optional: include 1s audio snippet in the detection event
    include_audio_snippet: bool = field(
        default_factory=lambda: os.getenv("INCLUDE_AUDIO_SNIPPET", "false").lower() == "true"
    )
    # Snippet buffer: 1 second = 16000 samples
    snippet_samples: int = 16000


config = Config()
