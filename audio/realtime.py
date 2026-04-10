from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Literal

import numpy as np
import sounddevice as sd

from audio.sample_library import SampleLibrary
from engine.pattern import Bar, Pattern
from engine.rhythm_tree import RhythmNode
from engine.timing import bar_duration_seconds


@dataclass(frozen=True)
class PreparedTriggerEvent:
    trigger_frame: int
    source_bar_index: int
    chain_position: int | None
    leaf: RhythmNode


@dataclass(frozen=True)
class PreparedLoopTransport:
    mode: Literal["bar", "pattern", "chain"]
    loop_frames: int
    events: list[PreparedTriggerEvent]


@dataclass(frozen=True)
class TransportSegment:
    start_frame: int
    end_frame: int
    source_bar_index: int
    chain_position: int | None


@dataclass(frozen=True)
class TransportStateSnapshot:
    is_playing: bool
    mode: Literal["bar", "pattern", "chain"] | None
    loop_length_frames: int
    playhead_frame: int
    loop_progress: float
    current_bar_index: int | None
    current_chain_position: int | None
    current_chain_bar_index: int | None
    status_message: str | None
    last_stop_reason: str | None


@dataclass
class ActiveVoice:
    audio: np.ndarray
    frame_position: int
    gain: float


class RealtimeLooper:
    """Callback-driven looping playback for bar, pattern, or chain loop transports."""

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
        self._segments: list[TransportSegment] = []
        self._event_index: int = 0
        self._playhead_frame: int = 0
        self._voices: list[ActiveVoice] = []
        self._is_playing: bool = False
        self._status_message: str | None = None
        self._last_stop_reason: str | None = None

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._is_playing

    @property
    def mode(self) -> Literal["bar", "pattern", "chain"] | None:
        with self._lock:
            if self._transport is None:
                return None
            return self._transport.mode

    def describe_transport(self) -> str:
        with self._lock:
            if self._transport is None:
                return "No realtime transport prepared."
            return (
                f"mode={self._transport.mode} "
                f"loop_frames={self._transport.loop_frames} "
                f"events={len(self._transport.events)}"
            )

    def transport_snapshot(self) -> TransportStateSnapshot:
        with self._lock:
            if self._transport is None:
                return TransportStateSnapshot(
                    is_playing=self._is_playing,
                    mode=None,
                    loop_length_frames=0,
                    playhead_frame=0,
                    loop_progress=0.0,
                    current_bar_index=None,
                    current_chain_position=None,
                    current_chain_bar_index=None,
                    status_message=self._status_message,
                    last_stop_reason=self._last_stop_reason,
                )

            loop_length = max(1, self._transport.loop_frames)
            playhead = min(max(self._playhead_frame, 0), loop_length - 1)
            progress = playhead / loop_length
            current_segment = self._segment_for_frame_locked(playhead)

            current_bar_index = current_segment.source_bar_index if current_segment is not None else None
            current_chain_position = current_segment.chain_position if current_segment is not None else None
            current_chain_bar_index = current_segment.source_bar_index if current_segment is not None else None

            return TransportStateSnapshot(
                is_playing=self._is_playing,
                mode=self._transport.mode,
                loop_length_frames=self._transport.loop_frames,
                playhead_frame=playhead,
                loop_progress=max(0.0, min(1.0, progress)),
                current_bar_index=current_bar_index,
                current_chain_position=current_chain_position,
                current_chain_bar_index=current_chain_bar_index,
                status_message=self._status_message,
                last_stop_reason=self._last_stop_reason,
            )

    def set_bar_loop(self, bar: Bar, bpm: float | None = None) -> None:
        with self._lock:
            bpm_value = self._bpm if bpm is None else float(bpm)
            self._transport, self._segments = self._prepare_sequence_transport_locked(
                mode="bar",
                bars=[bar],
                source_indices=[0],
                bpm=bpm_value,
            )
            self._reset_playback_state_locked()
            self._status_message = "Bar loop prepared."

    def set_pattern_loop(self, pattern: Pattern, bpm: float | None = None) -> None:
        with self._lock:
            if len(pattern.bars) == 0:
                raise ValueError("Cannot prepare realtime pattern loop: pattern has no bars.")
            bpm_value = self._bpm if bpm is None else float(bpm)
            order = list(range(len(pattern.bars)))
            self._transport, self._segments = self._prepare_sequence_transport_locked(
                mode="pattern",
                bars=pattern.bars,
                source_indices=order,
                bpm=bpm_value,
            )
            self._reset_playback_state_locked()
            self._status_message = "Pattern loop prepared."

    def set_chain_loop(self, pattern: Pattern, bpm: float | None = None) -> None:
        with self._lock:
            order = pattern.playback_order
            if order is None:
                raise ValueError("Cannot start chain loop: no playback order defined.")
            if len(order) == 0:
                raise ValueError("Cannot start chain loop: no playback order defined.")
            try:
                Pattern.validate_playback_order(order, len(pattern.bars))
            except ValueError as exc:
                raise ValueError("Cannot start chain loop: invalid playback order.") from exc

            bpm_value = self._bpm if bpm is None else float(bpm)
            bars = [pattern.bars[index] for index in order]
            self._transport, self._segments = self._prepare_sequence_transport_locked(
                mode="chain",
                bars=bars,
                source_indices=order,
                bpm=bpm_value,
            )
            self._reset_playback_state_locked()
            self._status_message = "Chain loop prepared."

    def start(self) -> None:
        sample_rate = self._sample_library.sample_rate
        if sample_rate is None:
            raise ValueError("Cannot start realtime playback: no samples loaded.")

        self._ensure_stream(sample_rate)
        with self._lock:
            if self._transport is None:
                raise ValueError("Cannot start realtime playback: no prepared transport.")
            self._is_playing = True
            self._status_message = "Playback running."
            self._last_stop_reason = None

        assert self._stream is not None
        if not self._stream.active:
            self._stream.start()

    def stop(self, reason: str | None = None) -> None:
        with self._lock:
            self._is_playing = False
            self._reset_playback_state_locked()
            resolved_reason = reason or "stopped by user action"
            self._last_stop_reason = resolved_reason
            self._status_message = f"Stopped: {resolved_reason}."

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

    def _prepare_sequence_transport_locked(
        self,
        *,
        mode: Literal["bar", "pattern", "chain"],
        bars: list[Bar],
        source_indices: list[int],
        bpm: float,
    ) -> tuple[PreparedLoopTransport, list[TransportSegment]]:
        sample_rate = self._sample_library.sample_rate
        if sample_rate is None:
            raise ValueError("Cannot prepare realtime transport: no samples loaded.")
        if len(bars) == 0:
            raise ValueError("Cannot prepare realtime transport: no bars.")

        self._channels = self._sample_library.output_channels()

        events: list[PreparedTriggerEvent] = []
        segments: list[TransportSegment] = []
        bar_start = 0
        for chain_position, (source_bar_index, bar) in enumerate(zip(source_indices, bars)):
            bar_frames = self._bar_frame_count(bar, bpm, sample_rate)
            segment_chain_position = None if mode == "bar" else chain_position
            segments.append(
                TransportSegment(
                    start_frame=bar_start,
                    end_frame=bar_start + bar_frames,
                    source_bar_index=source_bar_index,
                    chain_position=segment_chain_position,
                )
            )
            events.extend(
                self._prepare_events_for_bar(
                    bar=bar,
                    source_bar_index=source_bar_index,
                    chain_position=segment_chain_position,
                    bar_start_frame=bar_start,
                    bar_frames=bar_frames,
                )
            )
            bar_start += bar_frames

        events.sort(key=lambda e: e.trigger_frame)
        return PreparedLoopTransport(mode=mode, loop_frames=max(1, bar_start), events=events), segments

    def _prepare_events_for_bar(
        self,
        *,
        bar: Bar,
        source_bar_index: int,
        chain_position: int | None,
        bar_start_frame: int,
        bar_frames: int,
    ) -> list[PreparedTriggerEvent]:
        events: list[PreparedTriggerEvent] = []
        for leaf in bar.root.iter_leaves():
            if leaf.sample_slot is None:
                continue

            trigger_frame_local = int(round(leaf.start_fraction * bar_frames))
            trigger_frame_local = max(0, min(bar_frames - 1, trigger_frame_local))
            trigger_frame = bar_start_frame + trigger_frame_local

            events.append(
                PreparedTriggerEvent(
                    trigger_frame=trigger_frame,
                    source_bar_index=source_bar_index,
                    chain_position=chain_position,
                    leaf=leaf,
                )
            )

        events.sort(key=lambda e: e.trigger_frame)
        return events

    def _bar_frame_count(self, bar: Bar, bpm: float, sample_rate: int) -> int:
        bar_seconds = bar_duration_seconds(bar.time_signature, bpm)
        return max(1, int(round(bar_seconds * sample_rate)))

    def _segment_for_frame_locked(self, frame: int) -> TransportSegment | None:
        if not self._segments:
            return None
        for segment in self._segments:
            if segment.start_frame <= frame < segment.end_frame:
                return segment
        return self._segments[-1]

    def _trigger_events_in_span_locked(self, start_frame: int, end_frame: int) -> None:
        assert self._transport is not None
        while self._event_index < len(self._transport.events):
            event = self._transport.events[self._event_index]
            if event.trigger_frame >= end_frame:
                break
            if event.trigger_frame >= start_frame:
                maybe_voice = self._voice_for_prepared_event_locked(event)
                if maybe_voice is not None:
                    self._voices.append(maybe_voice)
            self._event_index += 1

    def _voice_for_prepared_event_locked(self, event: PreparedTriggerEvent) -> ActiveVoice | None:
        slot = event.leaf.sample_slot
        if slot is None:
            return None

        try:
            sample = self._sample_library.get(slot)
        except ValueError:
            return None

        audio = sample.audio
        if audio.shape[1] == 1 and self._channels == 2:
            audio = np.repeat(audio, repeats=2, axis=1)
        elif audio.shape[1] == 2 and self._channels == 1:
            audio = audio.mean(axis=1, keepdims=True)

        gain = float(event.leaf.velocity) * self._headroom_gain
        return ActiveVoice(audio=audio, frame_position=0, gain=gain)

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

    def _audio_callback(self, outdata: np.ndarray, frames: int, _time: sd.CallbackFlags, status: sd.CallbackFlags) -> None:
        outdata.fill(0.0)

        if status:
            with self._lock:
                self._status_message = f"Audio callback status: {status}"

        with self._lock:
            if not self._is_playing or self._transport is None:
                return

            loop_frames = self._transport.loop_frames
            if loop_frames <= 0:
                return

            callback_start = self._playhead_frame
            callback_end = callback_start + frames

            if callback_end <= loop_frames:
                self._trigger_events_in_span_locked(callback_start, callback_end)
            else:
                self._trigger_events_in_span_locked(callback_start, loop_frames)
                self._event_index = 0
                self._trigger_events_in_span_locked(0, callback_end - loop_frames)

            self._mix_voices_locked(outdata)

            self._playhead_frame = callback_end % loop_frames
            if callback_end >= loop_frames:
                self._event_index = 0
                while self._event_index < len(self._transport.events):
                    if self._transport.events[self._event_index].trigger_frame >= self._playhead_frame:
                        break
                    self._event_index += 1

        np.clip(outdata, -1.0, 1.0, out=outdata)
