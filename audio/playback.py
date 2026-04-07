from __future__ import annotations

import numpy as np
import sounddevice as sd


def play_once(buffer: np.ndarray, sample_rate: int) -> None:
    """Play rendered audio once and block until completion."""
    if buffer.ndim != 2:
        raise ValueError("Expected buffer shape (frames, channels).")
    sd.play(buffer, samplerate=sample_rate, blocking=True)
    sd.stop()
