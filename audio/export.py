from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from audio.renderer import OfflineRenderer
from audio.sample_library import SampleLibrary
from engine.pattern import Pattern


def _resolve_bpm(pattern: Pattern) -> float:
    bpm = getattr(pattern, "bpm", 120.0)
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

    renderer = OfflineRenderer(headroom_gain=1.0)
    bpm = _resolve_bpm(pattern)
    rendered = renderer.render_pattern(pattern, sample_library, bpm=bpm)
    audio = _normalize_audio(rendered.buffer, enabled=normalize)

    prefix = _safe_prefix(filename_prefix)
    file_path = output_dir / f"{prefix}_bpm{_format_bpm_tag(bpm)}.wav"
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
    bpm = _resolve_bpm(pattern)
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
