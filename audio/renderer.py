from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from audio.sample_library import SampleLibrary
from engine.events import SequencerEvent
from engine.pattern import Pattern
from engine.timing import bar_duration_seconds


@dataclass
class RenderResult:
    buffer: np.ndarray  # (frames, channels)
    sample_rate: int
    peak: float
    duration_seconds: float


class OfflineRenderer:
    """Simple offline one-pass renderer for one-pattern output."""

    def __init__(self, headroom_gain: float = 0.9) -> None:
        if not (0.0 < headroom_gain <= 1.0):
            raise ValueError("headroom_gain must be in (0,1].")
        self.headroom_gain = headroom_gain

    def render_pattern(self, pattern: Pattern, events: list[SequencerEvent], sample_library: SampleLibrary, bpm: float) -> RenderResult:
        if sample_library.sample_rate is None:
            raise ValueError("Sample library has no sample_rate; load at least one sample first.")

        sr = sample_library.sample_rate
        out_channels = sample_library.output_channels()

        total_seconds = 0.0
        for bar in pattern.bars:
            total_seconds += bar_duration_seconds(bar.time_signature, bpm)

        total_frames = max(1, int(np.ceil(total_seconds * sr)))
        output = np.zeros((total_frames, out_channels), dtype=np.float32)

        bar_start_seconds_accum = []
        t = 0.0
        for bar in pattern.bars:
            bar_start_seconds_accum.append(t)
            t += bar_duration_seconds(bar.time_signature, bpm)

        for ev in events:
            if ev.sample_slot is None:
                continue
            sample = sample_library.get(ev.sample_slot)
            bar = pattern.bars[ev.bar_index]
            bar_secs = bar_duration_seconds(bar.time_signature, bpm)
            ev_start_secs = bar_start_seconds_accum[ev.bar_index] + ev.start_fraction * bar_secs
            start_frame = int(round(ev_start_secs * sr))

            src = sample.audio
            if src.shape[1] == 1 and out_channels == 2:
                src = np.repeat(src, repeats=2, axis=1)
            if src.shape[1] == 2 and out_channels == 1:
                src = src.mean(axis=1, keepdims=True)

            src = src * float(ev.velocity)
            end_frame = min(total_frames, start_frame + src.shape[0])
            if end_frame <= start_frame:
                continue

            output[start_frame:end_frame, :] += src[: end_frame - start_frame, :]

        # Predictable anti-clipping strategy for Phase 1a:
        # Apply fixed headroom gain after summing overlaps.
        output *= self.headroom_gain

        peak = float(np.max(np.abs(output))) if output.size > 0 else 0.0
        return RenderResult(buffer=output, sample_rate=sr, peak=peak, duration_seconds=total_seconds)
