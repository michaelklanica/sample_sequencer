from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


MAX_SLOTS = 16


@dataclass
class SampleData:
    path: Path
    audio: np.ndarray  # shape: (frames, channels)
    sample_rate: int

    @property
    def channels(self) -> int:
        return int(self.audio.shape[1])


class SampleLibrary:
    """Fixed-size 16-slot WAV sample library."""

    def __init__(self) -> None:
        self.slots: list[SampleData | None] = [None] * MAX_SLOTS
        self.sample_rate: int | None = None

    def _validate_slot(self, slot: int) -> None:
        if slot < 0 or slot >= MAX_SLOTS:
            raise ValueError(f"Slot index out of range: {slot}. Valid range is 0-{MAX_SLOTS - 1}.")

    def load_wav_into_slot(self, slot: int, wav_path: Path) -> None:
        self._validate_slot(slot)
        wav_path = Path(wav_path)
        if not wav_path.exists():
            raise FileNotFoundError(f"Sample file not found: {wav_path}")

        audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
        if self.sample_rate is None:
            self.sample_rate = int(sr)
        elif int(sr) != self.sample_rate:
            raise ValueError(
                f"Sample rate mismatch for {wav_path.name}: {sr} != {self.sample_rate}. "
                "All WAVs must share one sample rate in Phase 1a."
            )

        self.slots[slot] = SampleData(path=wav_path, audio=audio.astype(np.float32, copy=False), sample_rate=int(sr))

    def auto_load_folder(self, folder: Path) -> int:
        folder = Path(folder)
        if not folder.exists() or not folder.is_dir():
            raise FileNotFoundError(f"Sample folder does not exist: {folder}")

        wavs = sorted(folder.glob("*.wav")) + sorted(folder.glob("*.WAV"))
        free_slots = [idx for idx, item in enumerate(self.slots) if item is None]

        loaded = 0
        for wav, slot in zip(wavs, free_slots):
            self.load_wav_into_slot(slot, wav)
            loaded += 1
        return loaded

    def get(self, slot: int) -> SampleData:
        self._validate_slot(slot)
        data = self.slots[slot]
        if data is None:
            raise ValueError(f"No sample loaded in slot {slot}.")
        return data

    def loaded_slots(self) -> list[int]:
        return [i for i, s in enumerate(self.slots) if s is not None]

    def output_channels(self) -> int:
        channels = [s.channels for s in self.slots if s is not None]
        if not channels:
            return 1
        return 2 if any(ch == 2 for ch in channels) else 1

    def debug_summary(self) -> str:
        lines = ["SampleLibrary:"]
        lines.append(f"  sample_rate: {self.sample_rate}")
        lines.append(f"  loaded_slots: {self.loaded_slots()}")
        for idx, sample in enumerate(self.slots):
            if sample is None:
                continue
            lines.append(
                f"  slot {idx:02d}: {sample.path.name} "
                f"(frames={sample.audio.shape[0]}, channels={sample.channels})"
            )
        return "\n".join(lines)
