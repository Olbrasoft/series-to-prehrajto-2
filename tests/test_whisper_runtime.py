"""Keep audio sampling independent of Ubuntu mirrors and package-manager delays."""

import subprocess
import sys
from types import SimpleNamespace

import pytest

from src.setup_whisper_runtime import configure_ffmpeg


@pytest.fixture
def packaged_binary(tmp_path, monkeypatch):
    executable = tmp_path / 'packaged-ffmpeg'
    executable.write_text('#!/bin/sh\necho "ffmpeg fixture"\n')
    executable.chmod(0o700)
    monkeypatch.setitem(sys.modules, 'imageio_ffmpeg', SimpleNamespace(get_ffmpeg_exe=lambda: str(executable)))
    # No apt, sudo, or preinstalled ffmpeg is discoverable.
    monkeypatch.setenv('PATH', str(tmp_path))
    return executable


def test_packaged_binary_is_runnable_and_published_for_following_steps(tmp_path, packaged_binary):
    path_file = tmp_path / 'github-path'
    command = configure_ffmpeg(tmp_path / 'bin', path_file)
    assert command.resolve() == packaged_binary
    assert subprocess.check_output([str(command), '-version'], text=True).strip() == 'ffmpeg fixture'
    assert path_file.read_text() == str(command.parent) + '\n'


def test_existing_managed_symlink_can_be_reused(tmp_path, packaged_binary):
    first = configure_ffmpeg(tmp_path / 'bin')
    assert configure_ffmpeg(tmp_path / 'bin') == first
    assert first.resolve() == packaged_binary


def test_broken_binary_fails_before_publishing_an_audio_runtime(tmp_path, packaged_binary):
    packaged_binary.write_text('#!/bin/sh\nexit 17\n')
    path_file = tmp_path / 'github-path'
    with pytest.raises(subprocess.CalledProcessError):
        configure_ffmpeg(tmp_path / 'bin', path_file)
    assert not path_file.exists()
    assert not (tmp_path / 'bin/ffmpeg').exists()


def test_setup_does_not_overwrite_an_unrelated_executable(tmp_path, packaged_binary):
    directory = tmp_path / 'bin'
    directory.mkdir()
    command = directory / 'ffmpeg'
    command.write_text('keep existing executable')
    with pytest.raises(FileExistsError):
        configure_ffmpeg(directory)
    assert command.read_text() == 'keep existing executable'
