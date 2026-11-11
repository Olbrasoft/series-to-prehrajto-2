"""Recover audio extraction after a native FFmpeg crash, with bounded isolation."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_with_audio_fallback(command, *, source, output, start, seconds,
                            timeout, text=False, headers=None):
    result = subprocess.run(command, capture_output=True, text=text, timeout=timeout)
    if result.returncode >= 0:
        return result
    # Static FFmpeg builds can crash in HTTPS input. Pass signed URLs on stdin,
    # never in diagnostics; isolate the alternate native decoder as well.
    payload = json.dumps(dict(source=source, output=str(output), start=start,
                              seconds=seconds, headers=headers or {}))
    recovered = subprocess.run([sys.executable, str(Path(__file__).resolve())],
                               input=payload if text else payload.encode(),
                               capture_output=True, text=text, timeout=timeout)
    return recovered


def decode_sample(*, source, output, start, seconds, headers):
    import av
    import numpy as np
    import wave

    rate = 16000
    if start < 0 or not 0 < seconds <= 3600:
        raise ValueError("Invalid sample interval")
    count = round(seconds * rate)
    samples = np.zeros(count, dtype=np.int16)
    covered = np.zeros(count, dtype=bool)
    options = {"headers": "".join(f"{k}: {v}\r\n" for k, v in headers.items())} if headers else {}
    with av.open(source, timeout=(10, 20), options=options) as container:
        if not container.streams.audio:
            raise ValueError("Missing audio stream")
        stream = container.streams.audio[0]
        origin = (container.start_time or 0) / av.time_base
        beginning = origin + start
        container.seek(round(beginning * av.time_base), backward=True)
        resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)

        def consume(frame):
            if frame.time is None:
                raise ValueError("Missing audio timestamps")
            position = round((frame.time - beginning) * rate)
            low, high = max(0, position), min(count, position + frame.samples)
            if high > low:
                values = frame.to_ndarray().reshape(-1)
                samples[low:high] = values[low - position:high - position]
                covered[low:high] = True
            return position + frame.samples >= count

        finished = False
        for frame in container.decode(stream):
            for converted in resampler.resample(frame):
                finished = consume(converted) or finished
            if finished:
                break
        if not finished:
            for converted in resampler.resample(None):
                consume(converted)
    # Preserve the original timeline including small gaps; incomplete or sparse
    # samples cannot become subtitle timing evidence.
    if covered.sum() < count * .99 or not covered[-min(count, 160):].any():
        raise ValueError("Incomplete audio interval")
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.astype("<i2", copy=False).tobytes())


if __name__ == "__main__":
    try:
        decode_sample(**json.load(sys.stdin))
    except Exception as error:
        # Native decoder messages can contain credential-bearing media URLs.
        print(f"Audio fallback failed: {type(error).__name__}", file=sys.stderr)
        raise SystemExit(1)
