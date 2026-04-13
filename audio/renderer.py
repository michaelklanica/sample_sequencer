from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from audio.sample_library import SampleLibrary
from engine.pattern import Bar, Pattern
from engine.timeline import TimelineEvent, build_timeline_events, pattern_duration_seconds


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

    def _render_into_buffer(self, output: np.ndarray, sample_library: SampleLibrary, start_seconds: float, sample_slot: int, velocity: float) -> None:
        sr = sample_library.sample_rate
        if sr is None:
            raise ValueError("Sample library has no sample_rate; load at least one sample first.")
        out_channels = sample_library.output_channels()

        sample = sample_library.get(sample_slot)
        start_frame = int(round(start_seconds * sr))

        src = sample.audio
        if src.shape[1] == 1 and out_channels == 2:
            src = np.repeat(src, repeats=2, axis=1)
        if src.shape[1] == 2 and out_channels == 1:
            src = src.mean(axis=1, keepdims=True)

        src = src * float(velocity)
        end_frame = min(output.shape[0], start_frame + src.shape[0])
        if end_frame <= start_frame:
            return

        output[start_frame:end_frame, :] += src[: end_frame - start_frame, :]

    def _render_events(
        self,
        events: list[TimelineEvent],
        total_seconds: float,
        sample_library: SampleLibrary,
    ) -> RenderResult:
        if sample_library.sample_rate is None:
            raise ValueError("Sample library has no sample_rate; load at least one sample first.")

        sr = sample_library.sample_rate
        out_channels = sample_library.output_channels()
        total_frames = max(1, int(np.ceil(total_seconds * sr)))
        output = np.zeros((total_frames, out_channels), dtype=np.float32)

        for event in events:
            if event.sample_slot is None:
                continue
            try:
                self._render_into_buffer(output, sample_library, event.start_seconds, event.sample_slot, event.velocity)
            except KeyError:
                # Missing sample slots are skipped to keep rendering resilient in editing workflows.
                continue

        output *= self.headroom_gain
        peak = float(np.max(np.abs(output))) if output.size > 0 else 0.0
        return RenderResult(buffer=output, sample_rate=sr, peak=peak, duration_seconds=total_seconds)

    def render_pattern(self, pattern: Pattern, sample_library: SampleLibrary, bpm: float) -> RenderResult:
        total_seconds = pattern_duration_seconds(pattern, bpm)
        return self._render_events(build_timeline_events(pattern, bpm), total_seconds, sample_library)

    def render_pattern_with_length(
        self,
        pattern: Pattern,
        sample_library: SampleLibrary,
        bpm: float,
        total_seconds: float,
        cycle_count: int = 1,
    ) -> RenderResult:
        if cycle_count < 1:
            raise ValueError("cycle_count must be >= 1.")
        if total_seconds <= 0:
            raise ValueError("total_seconds must be > 0.")

        cycle_duration = pattern_duration_seconds(pattern, bpm)
        base_events = build_timeline_events(pattern, bpm)
        events: list[TimelineEvent] = []
        for cycle_index in range(cycle_count):
            offset = cycle_index * cycle_duration
            for event in base_events:
                events.append(
                    TimelineEvent(
                        chain_position=event.chain_position,
                        source_bar_index=event.source_bar_index,
                        start_seconds=event.start_seconds + offset,
                        local_start_fraction=event.local_start_fraction,
                        local_duration_fraction=event.local_duration_fraction,
                        sample_slot=event.sample_slot,
                        velocity=event.velocity,
                        pitch_offset=event.pitch_offset,
                    )
                )

        return self._render_events(events, total_seconds=total_seconds, sample_library=sample_library)

    def render_bar(self, bar: Bar, sample_library: SampleLibrary, bpm: float) -> RenderResult:
        single_bar_pattern = Pattern(bars=[bar])
        return self.render_pattern(single_bar_pattern, sample_library, bpm)
