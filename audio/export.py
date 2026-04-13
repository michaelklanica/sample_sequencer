from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from audio.renderer import OfflineRenderer
from audio.sample_library import SampleLibrary
from engine.pattern import Pattern
from engine.project import Project
from engine.timeline import pattern_duration_seconds


EXPORT_MODES = ("truncate", "wrap", "tail")
MAX_TAIL_SECONDS = 20.0


def _resolve_bpm(bpm: float) -> float:
    return float(bpm)


def _format_bpm_tag(bpm: float) -> str:
    if float(bpm).is_integer():
        return str(int(bpm))
    return f"{bpm:.2f}".rstrip("0").rstrip(".")


def _safe_prefix(prefix: str) -> str:
    normalized = "_".join(prefix.strip().split())
    return normalized or "pattern"


def _normalize_audio(audio: np.ndarray, enabled: bool) -> np.ndarray:
    out = np.asarray(audio, dtype=np.float32)
    if not enabled or out.size == 0:
        return out

    peak = float(np.max(np.abs(out)))
    if peak <= 1e-12:
        return out

    return out * (0.98 / peak)


def export_pattern(
    pattern: Pattern,
    sample_library: SampleLibrary,
    output_path: str,
    filename_prefix: str,
    sample_rate: int = 44100,
    normalize: bool = True,
    mode: str = "truncate",
    bpm: float = 120.0,
) -> str:
    """
    Renders full pattern (respecting playback chain) and writes to WAV.

    Returns full file path.
    """
    output_dir = Path(output_path).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if sample_library.sample_rate is not None and sample_library.sample_rate != sample_rate:
        raise ValueError(
            f"Sample library sample_rate is {sample_library.sample_rate}; cannot export at requested {sample_rate}."
        )

    normalized_mode = mode.strip().lower()
    if normalized_mode not in EXPORT_MODES:
        raise ValueError(f"Unsupported export mode '{mode}'. Expected one of: {', '.join(EXPORT_MODES)}.")

    renderer = OfflineRenderer(headroom_gain=1.0)
    resolved_bpm = _resolve_bpm(bpm)
    cycle_duration = pattern_duration_seconds(pattern, bpm=resolved_bpm)

    if normalized_mode == "truncate":
        rendered = renderer.render_pattern(pattern, sample_library, bpm=resolved_bpm)
        audio = rendered.buffer
    elif normalized_mode == "wrap":
        rendered = renderer.render_pattern_with_length(
            pattern,
            sample_library,
            bpm=resolved_bpm,
            total_seconds=2.0 * cycle_duration,
            cycle_count=2,
        )
        split_frame = max(1, int(round(cycle_duration * rendered.sample_rate)))
        first = rendered.buffer[:split_frame, :]
        second = rendered.buffer[split_frame : split_frame * 2, :]
        if second.shape[0] < first.shape[0]:
            second = np.pad(second, ((0, first.shape[0] - second.shape[0]), (0, 0)))
        audio = first + second[: first.shape[0], :]
    else:
        slot_lengths: list[float] = []
        if sample_library.sample_rate:
            for slot in sample_library.loaded_slots():
                sample = sample_library.get(slot)
                slot_lengths.append(float(sample.audio.shape[0]) / float(sample_library.sample_rate))
        max_tail = min(max(slot_lengths, default=0.0), MAX_TAIL_SECONDS)
        rendered = renderer.render_pattern_with_length(
            pattern,
            sample_library,
            bpm=resolved_bpm,
            total_seconds=cycle_duration + max_tail,
            cycle_count=1,
        )
        audio = rendered.buffer

    audio = _normalize_audio(audio, enabled=normalize)

    prefix = _safe_prefix(filename_prefix)
    file_path = output_dir / f"{prefix}_bpm{_format_bpm_tag(resolved_bpm)}_{normalized_mode}.wav"
    sf.write(file_path, audio, samplerate=rendered.sample_rate)
    return str(file_path)


def export_bars(
    pattern: Pattern,
    sample_library: SampleLibrary,
    output_dir: str,
    filename_prefix: str,
    sample_rate: int = 44100,
    normalize: bool = True,
) -> list[str]:
    """
    Renders each bar independently and writes separate WAV files.

    Returns list of file paths.
    """
    target_dir = Path(output_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    if sample_library.sample_rate is not None and sample_library.sample_rate != sample_rate:
        raise ValueError(
            f"Sample library sample_rate is {sample_library.sample_rate}; cannot export at requested {sample_rate}."
        )

    renderer = OfflineRenderer(headroom_gain=1.0)
    bpm = _resolve_bpm(120.0)
    prefix = _safe_prefix(filename_prefix)

    exported_files: list[str] = []
    for bar_index, bar in enumerate(pattern.bars, start=1):
        rendered = renderer.render_bar(bar, sample_library, bpm=bpm)
        audio = _normalize_audio(rendered.buffer, enabled=normalize)
        ts = bar.time_signature
        file_path = target_dir / f"{prefix}_bar{bar_index:02d}_{ts.numerator}-{ts.denominator}.wav"
        sf.write(file_path, audio, samplerate=rendered.sample_rate)
        exported_files.append(str(file_path))

    return exported_files


def export_arrangement(
    project: Project,
    sample_library: SampleLibrary,
    output_path: str,
    filename_prefix: str,
    sample_rate: int = 44100,
    normalize: bool = True,
    mode: str = "truncate",
    bpm: float = 120.0,
) -> str:
    arranged_bars = []
    for pattern_index in project.arrangement:
        if 0 <= pattern_index < len(project.patterns):
            arranged_bars.extend([bar.clone() for bar in project.patterns[pattern_index].bars])
    if not arranged_bars:
        arranged_bars = [bar.clone() for bar in project.current_pattern.bars]
    arrangement_pattern = Pattern(name="Arrangement", bars=arranged_bars)
    return export_pattern(
        arrangement_pattern,
        sample_library,
        output_path=output_path,
        filename_prefix=filename_prefix,
        sample_rate=sample_rate,
        normalize=normalize,
        mode=mode,
        bpm=bpm,
    )
