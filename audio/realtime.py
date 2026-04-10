from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Literal

import numpy as np
import sounddevice as sd

from audio.sample_library import SampleLibrary
from engine.pattern import Bar, Pattern
from engine.timing import bar_duration_seconds


@dataclass(frozen=True)
class PreparedTriggerEvent:
    trigger_frame: int
    source_bar_index: int
    sample_slot: int
    velocity: float
    audio: np.ndarray


@dataclass(frozen=True)
class PreparedLoopTransport:
    mode: Literal["bar", "pattern"]
    loop_frames: int
    events: list[PreparedTriggerEvent]


@dataclass
class ActiveVoice:
    audio: np.ndarray
    frame_position: int
    gain: float


class RealtimeLooper:
    """Callback-driven looping playback for a bar loop or full-pattern loop."""

    def __init__(self, sample_library: SampleLibrary, bpm: float, headroom_gain: float = 0.8) -> None:
        if bpm <= 0:
            raise ValueError("BPM must be > 0.")
        if headroom_gain <= 0.0 or headroom_gain > 1.0:
            raise ValueError("headroom_gain must be in (0.0, 1.0].")

        self._sample_library = sample_library
        self._bpm = float(bpm)
        self._headroom_gain = float(headroom_gain)

        self._lock = threading.Lock()
        self._stream: sd.OutputStream | None = None

        self._channels: int = 1

        self._transport: PreparedLoopTransport | None = None
        self._event_index: int = 0
        self._playhead_frame: int = 0
        self._voices: list[ActiveVoice] = []
        self._is_playing: bool = False

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._is_playing

    @property
    def mode(self) -> Literal["bar", "pattern"] | None:
        with self._lock:
            if self._transport is None:
                return None
            return self._transport.mode

    def set_bar_loop(self, bar: Bar, bpm: float | None = None) -> None:
        with self._lock:
            bpm_value = self._bpm if bpm is None else float(bpm)
            self._transport = self._prepare_bar_transport_locked(bar, bpm_value)
            self._reset_playback_state_locked()

    def set_pattern_loop(self, pattern: Pattern, bpm: float | None = None) -> None:
        with self._lock:
            bpm_value = self._bpm if bpm is None else float(bpm)
            self._transport = self._prepare_pattern_transport_locked(pattern, bpm_value)
            self._reset_playback_state_locked()

    def start(self) -> None:
        sample_rate = self._sample_library.sample_rate
        if sample_rate is None:
            raise ValueError("Cannot start realtime playback: no samples loaded.")

        self._ensure_stream(sample_rate)
        with self._lock:
            if self._transport is None:
                raise ValueError("Cannot start realtime playback: no prepared transport.")
            self._is_playing = True

        assert self._stream is not None
        if not self._stream.active:
            self._stream.start()

    def stop(self) -> None:
        with self._lock:
            self._is_playing = False
            self._reset_playback_state_locked()

    def shutdown(self) -> None:
        self.stop()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _ensure_stream(self, sample_rate: int) -> None:
        if self._stream is not None and self._stream.samplerate == sample_rate:
            return

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        self._channels = self._sample_library.output_channels()
        self._stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=self._channels,
            dtype="float32",
            callback=self._audio_callback,
            blocksize=0,
        )

    def _reset_playback_state_locked(self) -> None:
        self._event_index = 0
        self._playhead_frame = 0
        self._voices.clear()

    def _prepare_bar_transport_locked(self, bar: Bar, bpm: float) -> PreparedLoopTransport:
        sample_rate = self._sample_library.sample_rate
        if sample_rate is None:
            raise ValueError("Cannot prepare realtime transport: no samples loaded.")

        self._channels = self._sample_library.output_channels()
        bar_frames = self._bar_frame_count(bar, bpm, sample_rate)
        events = self._prepare_events_for_bar(bar=bar, bar_index=0, bar_start_frame=0, bar_frames=bar_frames)
        return PreparedLoopTransport(mode="bar", loop_frames=bar_frames, events=events)

    def _prepare_pattern_transport_locked(self, pattern: Pattern, bpm: float) -> PreparedLoopTransport:
        if len(pattern.bars) == 0:
            raise ValueError("Cannot prepare realtime pattern loop: pattern has no bars.")

        sample_rate = self._sample_library.sample_rate
        if sample_rate is None:
            raise ValueError("Cannot prepare realtime transport: no samples loaded.")

        self._channels = self._sample_library.output_channels()
        bar_frames = [self._bar_frame_count(bar, bpm, sample_rate) for bar in pattern.bars]

        events: list[PreparedTriggerEvent] = []
        bar_start = 0
        for bar_index, (bar, frames) in enumerate(zip(pattern.bars, bar_frames)):
            events.extend(
                self._prepare_events_for_bar(bar=bar, bar_index=bar_index, bar_start_frame=bar_start, bar_frames=frames)
            )
            bar_start += frames

        events.sort(key=lambda e: e.trigger_frame)
        loop_frames = max(1, sum(bar_frames))
        return PreparedLoopTransport(mode="pattern", loop_frames=loop_frames, events=events)

    def _prepare_events_for_bar(
        self,
        *,
        bar: Bar,
        bar_index: int,
        bar_start_frame: int,
        bar_frames: int,
    ) -> list[PreparedTriggerEvent]:
        events: list[PreparedTriggerEvent] = []
        for event in bar.flatten_events(bar_index=bar_index):
            if event.sample_slot is None:
                continue
            try:
                sample = self._sample_library.get(event.sample_slot)
            except ValueError:
                continue

            audio = sample.audio
            if audio.shape[1] == 1 and self._channels == 2:
                audio = np.repeat(audio, repeats=2, axis=1)
            elif audio.shape[1] == 2 and self._channels == 1:
                audio = audio.mean(axis=1, keepdims=True)

            trigger_frame_local = int(round(event.start_fraction * bar_frames))
            trigger_frame_local = max(0, min(bar_frames - 1, trigger_frame_local))
            trigger_frame = bar_start_frame + trigger_frame_local

            events.append(
                PreparedTriggerEvent(
                    trigger_frame=trigger_frame,
                    source_bar_index=bar_index,
                    sample_slot=event.sample_slot,
                    velocity=float(event.velocity),
                    audio=audio,
                )
            )

        events.sort(key=lambda e: e.trigger_frame)
        return events

    def _bar_frame_count(self, bar: Bar, bpm: float, sample_rate: int) -> int:
        bar_seconds = bar_duration_seconds(bar.time_signature, bpm)
        return max(1, int(round(bar_seconds * sample_rate)))

    def _trigger_events_in_span_locked(self, start_frame: int, end_frame: int) -> None:
        assert self._transport is not None
        while self._event_index < len(self._transport.events):
            event = self._transport.events[self._event_index]
            if event.trigger_frame >= end_frame:
                break
            if event.trigger_frame >= start_frame:
                self._voices.append(ActiveVoice(audio=event.audio, frame_position=0, gain=event.velocity * self._headroom_gain))
            self._event_index += 1

    def _mix_voices_locked(self, outdata: np.ndarray) -> None:
        if not self._voices:
            return

        out_frames = outdata.shape[0]
        next_voices: list[ActiveVoice] = []

        for voice in self._voices:
            remaining = voice.audio.shape[0] - voice.frame_position
            if remaining <= 0:
                continue

            take = min(out_frames, remaining)
            src = voice.audio[voice.frame_position : voice.frame_position + take, :]
            outdata[:take, :] += src * voice.gain
            voice.frame_position += take

            if voice.frame_position < voice.audio.shape[0]:
                next_voices.append(voice)

        self._voices = next_voices

    def _audio_callback(self, outdata: np.ndarray, frames: int, _time: sd.CallbackFlags, _status: sd.CallbackFlags) -> None:
        outdata.fill(0.0)

        with self._lock:
            if not self._is_playing or self._transport is None or self._transport.loop_frames <= 0:
                return

            loop_frames = self._transport.loop_frames
            remaining = frames
            span_start = self._playhead_frame
            while remaining > 0:
                span = min(loop_frames - span_start, remaining)
                span_end = span_start + span

                self._trigger_events_in_span_locked(span_start, span_end)
                remaining -= span
                span_start = span_end

                if span_start >= loop_frames:
                    span_start = 0
                    self._event_index = 0

            self._mix_voices_locked(outdata)
            self._playhead_frame = (self._playhead_frame + frames) % loop_frames


RealtimeBarLooper = RealtimeLooper
