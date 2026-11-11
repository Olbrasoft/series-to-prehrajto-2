"""Exercise network decoding and timestamp preservation after a native crash."""
import array
import functools
import http.server
import importlib.util
import subprocess
import sys
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audio_sampling import run_with_audio_fallback


class AudioFallbackTests(unittest.TestCase):
    def test_http_failure_does_not_retry_or_mask_the_error(self):
        failed = subprocess.CompletedProcess(["ffmpeg"], 1, "", "HTTP 403")
        with patch("audio_sampling.subprocess.run", return_value=failed) as run:
            result = run_with_audio_fallback(["ffmpeg"], source="unused", output="unused",
                                             start=0, seconds=1, timeout=10, text=True)
        self.assertIs(result, failed)
        self.assertEqual(run.call_count, 1)

    @unittest.skipUnless(importlib.util.find_spec("av"), "PyAV is optional")
    def test_native_crash_recovers_http_audio_without_moving_timestamps(self):
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *_args):
                pass

        native_run = subprocess.run
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.wav", Path(directory) / "sample.wav"
            # Alternating one-second blocks make a wrong seek visible. Use a
            # non-frame-aligned start and verify the transitions sample by sample.
            data = array.array("h", (1000 if (i // 8000) % 2 == 0 else -1000
                                     for i in range(8000 * 5)))
            with wave.open(str(source), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(data.tobytes())
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                functools.partial(QuietHandler, directory=directory))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def execute(command, **kwargs):
                if command[0] == "broken-ffmpeg":
                    return subprocess.CompletedProcess(command, -11, "", "")
                return native_run(command, **kwargs)
            try:
                with patch("audio_sampling.subprocess.run", side_effect=execute):
                    result = run_with_audio_fallback(["broken-ffmpeg"],
                        source=f"http://127.0.0.1:{server.server_port}/input.wav", output=output,
                        start=1.123, seconds=2.25, timeout=10, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                with wave.open(str(output)) as wav:
                    self.assertEqual((wav.getframerate(), wav.getnchannels(), wav.getnframes()),
                                     (16000, 1, 36000))
                    pcm = array.array("h", wav.readframes(wav.getnframes()))
                for seconds, sign in ((.1, -1), (.8, -1), (.9, 1), (1.8, 1), (1.9, -1)):
                    self.assertGreater(sign * pcm[round(seconds * 16000)], 900)
                # The source transition at 2s belongs precisely at sample 14032.
                self.assertLess(pcm[14012], -900)
                self.assertGreater(pcm[14052], 900)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    @unittest.skipUnless(importlib.util.find_spec("av"), "PyAV is optional")
    def test_worker_failure_never_prints_a_signed_media_url(self):
        import json
        from audio_sampling import __file__ as helper
        secret_url = "https://127.0.0.1:1/no-media?token=private-secret"
        result = subprocess.run([sys.executable, helper], input=json.dumps(dict(
            source=secret_url, output="unused", start=0, seconds=1, headers={})),
            text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("private-secret", result.stdout + result.stderr)
        self.assertIn("Audio fallback failed:", result.stderr)
