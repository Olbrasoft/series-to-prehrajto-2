#!/usr/bin/env python3
"""Expose the wheel-packaged FFmpeg executable without an Ubuntu package install."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


def configure_ffmpeg(bin_dir: Path, github_path: Path | None = None) -> Path:
    from imageio_ffmpeg import get_ffmpeg_exe

    executable = Path(get_ffmpeg_exe()).resolve(strict=True)
    subprocess.run([str(executable), '-version'], check=True, capture_output=True,
                   text=True, timeout=10)
    bin_dir.mkdir(parents=True, exist_ok=True)
    command = bin_dir / 'ffmpeg'
    if command.is_symlink():
        if command.resolve() != executable:
            command.unlink()
            command.symlink_to(executable)
    else:
        # Refuse to overwrite an unrelated executable in the managed directory.
        command.symlink_to(executable)
    if github_path is not None:
        with github_path.open('a', encoding='utf-8') as output:
            output.write(str(bin_dir.resolve()) + '\n')
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', type=Path,
                        default=Path(os.environ.get('RUNNER_TEMP', tempfile.gettempdir())) / 'series-whisper-bin')
    args = parser.parse_args()
    path_file = Path(os.environ['GITHUB_PATH']) if os.environ.get('GITHUB_PATH') else None
    command = configure_ffmpeg(args.bin_dir, path_file)
    print(f'FFmpeg ready: {command}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
