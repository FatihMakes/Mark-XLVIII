import os
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import openwakeword
from openwakeword.model import Model
from openwakeword.utils import download_models


BASE_DIR = Path(__file__).resolve().parent
SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280
THRESHOLD = 0.5
DEBOUNCE_SECONDS = 2.0
CUSTOM_MODEL = BASE_DIR / "nee_how__ahh_niu.onnx"
FALLBACK_MODEL = "hey_jarvis"


def build_model(custom_model: str | Path = CUSTOM_MODEL):
    custom_model = Path(custom_model)
    if custom_model.exists():
        return Model(wakeword_models=[str(custom_model)], inference_framework="onnx")

    print(
        f"{custom_model.name} not found; using built-in openWakeWord model "
        f"'{FALLBACK_MODEL}'."
    )
    fallback_model_path = openwakeword.MODELS[FALLBACK_MODEL]["model_path"].replace(
        ".tflite", ".onnx"
    )
    if not os.path.exists(fallback_model_path):
        download_models([FALLBACK_MODEL])

    return Model(wakeword_models=[FALLBACK_MODEL], inference_framework="onnx")


class WakeWordDetector:
    def __init__(
        self,
        threshold: float = THRESHOLD,
        debounce_seconds: float = DEBOUNCE_SECONDS,
        frame_samples: int = FRAME_SAMPLES,
        model: Model | None = None,
    ):
        self.model = model or build_model()
        self.threshold = threshold
        self.debounce_seconds = debounce_seconds
        self.frame_samples = frame_samples
        self._buffer = np.empty(0, dtype=np.int16)
        self._last_detection = 0.0

    def process_bytes(self, data: bytes):
        if not data:
            return None
        return self.process_audio(np.frombuffer(data, dtype=np.int16))

    def process_audio(self, audio):
        samples = np.asarray(audio, dtype=np.int16).reshape(-1)
        if samples.size == 0:
            return None

        self._buffer = np.concatenate((self._buffer, samples))
        while self._buffer.size >= self.frame_samples:
            frame = self._buffer[: self.frame_samples].copy()
            self._buffer = self._buffer[self.frame_samples :]
            scores = self.model.predict(frame)
            now = time.monotonic()

            for name, confidence in scores.items():
                if (
                    confidence >= self.threshold
                    and now - self._last_detection >= self.debounce_seconds
                ):
                    self._last_detection = now
                    self._buffer = np.empty(0, dtype=np.int16)
                    return name, float(confidence)

        return None


def main():
    detector = WakeWordDetector()

    print("Listening for wake word. Press Ctrl+C to stop.")
    with sd.InputStream(
        channels=1,
        samplerate=SAMPLE_RATE,
        blocksize=FRAME_SAMPLES,
        dtype="int16",
    ) as stream:
        while True:
            frame, _ = stream.read(FRAME_SAMPLES)
            detection = detector.process_audio(np.squeeze(frame))
            if detection:
                name, confidence = detection
                print(f"Detected {name}! ({confidence:.2f})")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")
