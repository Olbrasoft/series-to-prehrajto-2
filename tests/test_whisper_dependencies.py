"""Exercise the real audio decoder without downloading a Whisper model."""

import array
import importlib.util
import math
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec("faster_whisper"), "Whisper is optional")
class WhisperDependencyTests(unittest.TestCase):
    def test_ffmpeg_extracts_audio_and_supports_https_sources(self):
        executable = shutil.which('ffmpeg')
        self.assertIsNotNone(executable)
        protocols = subprocess.check_output([executable, '-protocols'], text=True, timeout=10)
        self.assertIn('https', protocols.split())
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.wav'
            target = Path(directory) / 'sample.wav'
            with wave.open(str(source), 'wb') as output:
                output.setnchannels(2)
                output.setsampwidth(2)
                output.setframerate(8000)
                output.writeframes(b'\0\0\0\0' * 8000)
            subprocess.run([executable, '-y', '-hide_banner', '-loglevel', 'error',
                            '-i', str(source), '-vn', '-ac', '1', '-ar', '16000', str(target)],
                           check=True, capture_output=True, timeout=10)
            with wave.open(str(target)) as sample:
                self.assertEqual(sample.getnchannels(), 1)
                self.assertEqual(sample.getframerate(), 16000)
                self.assertEqual(sample.getnframes(), 16000)

    def test_decode_and_resample_wav(self):
        from faster_whisper.audio import decode_audio

        samples = array.array("h", (
            int(8000 * math.sin(2 * math.pi * 440 * i / 8000))
            for i in range(8000)
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.wav"
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(8000)
                output.writeframes(samples.tobytes())
            decoded = decode_audio(str(path), sampling_rate=16000)

        self.assertEqual(decoded.shape, (16000,))
        self.assertEqual(str(decoded.dtype), "float32")
        self.assertGreater(float(abs(decoded).max()), 0.1)
