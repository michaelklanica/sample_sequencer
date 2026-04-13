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


@dataclass
class OfflineVoice:
    audio: np.ndarray
    frame_position: int
    gain: float
    choke_group: int | None
    choke_fade_remaining_samples: int = 0
    choke_fade_total_samples: int = 0


class OfflineRenderer:
    """Simple offline one-pass renderer for one-pattern output."""
    CHOKE_FADE_MS = 5.0

    def __init__(self, headroom_gain: float = 0.9) -> None:
        if not (0.0 < headroom_gain <= 1.0):
            raise ValueError("headroom_gain must be in (0,1].")
        self.headroom_gain = headroom_gain

    def _prepare_voice(
        self,
        sample_library: SampleLibrary,
        sample_slot: int,
        velocity: float,
        out_channels: int,
    ) -> OfflineVoice | None:
        try:
            sample = sample_library.get(sample_slot)
        except ValueError:
            return None

        src = sample.audio
        if src.shape[1] == 1 and out_channels == 2:
            src = np.repeat(src, repeats=2, axis=1)
        if src.shape[1] == 2 and out_channels == 1:
            src = src.mean(axis=1, keepdims=True)
        return OfflineVoice(
            audio=src,
            frame_position=0,
            gain=float(velocity),
            choke_group=sample_library.choke_group(sample_slot),
        )

    def _choke_voices(
        self,
        voices: list[OfflineVoice],
        choke_group: int | None,
        fade_samples: int,
    ) -> None:
        if choke_group is None:
            return
        for voice in voices:
            if voice.choke_group != choke_group:
                continue
            voice.choke_fade_total_samples = fade_samples
            if voice.choke_fade_remaining_samples <= 0:
                voice.choke_fade_remaining_samples = fade_samples

    def _mix_voice_span(self, output: np.ndarray, start_frame: int, end_frame: int, voices: list[OfflineVoice]) -> list[OfflineVoice]:
        if not voices or end_frame <= start_frame:
            return voices
        length = end_frame - start_frame
        mixed = np.zeros((length, output.shape[1]), dtype=np.float32)
        next_voices: list[OfflineVoice] = []
        for voice in voices:
            remaining = voice.audio.shape[0] - voice.frame_position
            if remaining <= 0:
                continue
            take = min(length, remaining)
            src = voice.audio[voice.frame_position : voice.frame_position + take, :]
            scaled = src * voice.gain
            if voice.choke_fade_remaining_samples > 0 and voice.choke_fade_total_samples > 0:
                fade_take = min(take, voice.choke_fade_remaining_samples)
                fade_curve = (
                    np.arange(voice.choke_fade_remaining_samples, voice.choke_fade_remaining_samples - fade_take, -1)
                    / float(voice.choke_fade_total_samples)
                ).astype(np.float32, copy=False)
                scaled[:fade_take, :] *= fade_curve[:, np.newaxis]
                if fade_take < take:
                    scaled[fade_take:, :] = 0.0
                voice.choke_fade_remaining_samples = max(0, voice.choke_fade_remaining_samples - take)

            mixed[:take, :] += scaled
            voice.frame_position += take
            if voice.frame_position < voice.audio.shape[0] and (
                voice.choke_fade_total_samples == 0 or voice.choke_fade_remaining_samples > 0
            ):
                next_voices.append(voice)
        output[start_frame:end_frame, :] += mixed
        return next_voices

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
        fade_samples = max(1, int(sr * self.CHOKE_FADE_MS / 1000.0))
        sorted_events = sorted(events, key=lambda event: event.start_seconds)
        voices: list[OfflineVoice] = []
        render_cursor = 0

        for event in sorted_events:
            event_frame = int(round(event.start_seconds * sr))
            event_frame = max(0, min(total_frames, event_frame))
            voices = self._mix_voice_span(output, render_cursor, event_frame, voices)
            render_cursor = event_frame
            if event.sample_slot is None:
                continue
            voice = self._prepare_voice(sample_library, event.sample_slot, event.velocity, out_channels)
            if voice is None:
                continue
            self._choke_voices(voices, voice.choke_group, fade_samples)
            voices.append(voice)

        self._mix_voice_span(output, render_cursor, total_frames, voices)

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
