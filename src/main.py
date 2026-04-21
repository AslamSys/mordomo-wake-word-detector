"""
Main entry point — wake word detection service.

States:
  IDLE       — listening, running OpenWakeWord on every frame
  SUPPRESSED — ignoring audio, waiting for conversation.ended

NATS events:
  SUB conversation.started  → SUPPRESSED
  SUB conversation.ended    → IDLE
  PUB wake_word.detected    → on detection
"""
import asyncio
import base64
import json
import logging
import time
import uuid
from collections import deque
from enum import Enum

import numpy as np
import zmq
import nats

from src.config import config
from src.detector import WakeWordDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("wake-word-detector")


class State(Enum):
    IDLE = "idle"
    SUPPRESSED = "suppressed"


# ── Globals ───────────────────────────────────────────────────────────────────
_state = State.IDLE
_frame_sequence = 0
# Rolling 1-second audio buffer for optional snippet
_snippet_buffer: deque = deque(maxlen=config.snippet_samples)


# ── ZeroMQ receive loop (runs in thread) ──────────────────────────────────────
def _zmq_loop(detector: WakeWordDetector, detection_queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    global _state, _frame_sequence

    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.SUB)
    sock.connect(config.zmq_vad_url)
    sock.setsockopt_string(zmq.SUBSCRIBE, config.zmq_topic)
    sock.setsockopt(zmq.RCVTIMEO, 1000)  # 1s timeout so thread can exit cleanly

    logger.info(f"ZeroMQ SUB connected to {config.zmq_vad_url}, topic={config.zmq_topic}")

    last_telemetry = 0
    _received_frames = 0
    while True:
        try:
            parts = sock.recv_multipart()
        except zmq.Again:
            continue
        except zmq.ZMQError:
            break

        _received_frames += 1
        now = time.time()
        if now - last_telemetry > 5.0:
            logger.info(f"ZeroMQ SUB heartbeat: received {_received_frames} frames so far. Current buffer length: {len(_snippet_buffer)}")
            last_telemetry = now

        if len(parts) < 2:
            continue

        pcm_bytes = parts[1]
        _frame_sequence += 1

        # Keep rolling snippet buffer regardless of state
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        _snippet_buffer.extend(samples.tolist())

        if _state == State.SUPPRESSED:
            continue

        confidence = detector.process_frame(pcm_bytes)
        if confidence is not None:
            snippet_b64 = None
            if config.include_audio_snippet:
                snippet = np.array(list(_snippet_buffer), dtype=np.int16)
                snippet_b64 = base64.b64encode(snippet.tobytes()).decode()

            event = {
                "timestamp": time.time(),
                "confidence": confidence,
                "keyword": config.wake_word,
                "audio_snippet": snippet_b64,
                "sequence": _frame_sequence,
                "session_id": str(uuid.uuid4()),
            }
            loop.call_soon_threadsafe(detection_queue.put_nowait, event)

    sock.close()


# ── NATS handlers ─────────────────────────────────────────────────────────────
async def _on_conversation_started(msg):
    global _state
    if _state != State.SUPPRESSED:
        _state = State.SUPPRESSED
        logger.info("State → SUPPRESSED (conversation started)")


async def _on_conversation_ended(msg):
    global _state
    if _state != State.IDLE:
        _state = State.IDLE
        logger.info("State → IDLE (conversation ended)")


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    logger.info("Initializing wake word detector…")
    detector = WakeWordDetector(
        model_path=config.model_path,
        wake_word=config.wake_word,
        threshold=config.threshold,
        sample_rate=config.sample_rate,
    )

    loop = asyncio.get_event_loop()
    detection_queue: asyncio.Queue = asyncio.Queue()

    # ── NATS ──────────────────────────────────────────────────────────────
    try:
        async def error_cb(e):
            logger.error(f"NATS error: {e}")

        async def reconnected_cb():
            logger.warning("NATS reconnected")

        async def disconnected_cb():
            logger.warning("NATS disconnected")

        nc = await nats.connect(
            config.nats_url,
            error_cb=error_cb,
            reconnected_cb=reconnected_cb,
            disconnected_cb=disconnected_cb,
        )
        logger.info(f"Connected to NATS: {config.nats_url}")
        
        await nc.subscribe("mordomo.conversation.started", cb=_on_conversation_started)
        await nc.subscribe("mordomo.conversation.ended",   cb=_on_conversation_ended)
    except Exception as e:
        logger.warning(f"NATS unavailable: {e} — running without NATS (detection events will be lost)")
        nc = None

    # ── ZeroMQ loop in thread ─────────────────────────────────────────────
    executor_future = loop.run_in_executor(None, _zmq_loop, detector, detection_queue, loop)

    # ── Dispatch detection events ─────────────────────────────────────────
    logger.info(f"Listening for wake word '{config.wake_word}' (threshold={config.threshold})")
    try:
        while True:
            event = await detection_queue.get()
            logger.info(
                f"Wake word detected! confidence={event['confidence']:.3f} session={event['session_id']}"
            )
            if nc:
                await nc.publish("mordomo.wake_word.detected", json.dumps(event).encode())
                # Publish audio snippet separately for speaker-verification
                if event.get("audio_snippet"):
                    snippet_payload = json.dumps({
                        "audio_b64": event["audio_snippet"],
                        "sample_rate": config.sample_rate,
                        "session_id": event["session_id"],
                    }).encode()
                    await nc.publish("mordomo.audio.snippet", snippet_payload)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        executor_future.cancel()
        if nc:
            await nc.drain()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
