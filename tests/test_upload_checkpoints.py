import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from src import pick_next_episode as picker
from src import prepare_episode_sources as preparation
from src import build_upload_manifest as manifest
from src import sync_batch as sync
from src.upload_state_merge import merge_state


def intent(identifier='first', started='2026-11-01T12:00:00Z'):
    return dict(intent_id=identifier, started_at=started, episode_id=1, series_id=2,
                season=1, episode=1, source_id=7, upload_account='primary')


def test_committed_reservation_wins_and_completion_closes_stale_reservations():
    first, second = intent(), intent('second', '2026-11-01T12:01:00Z')
    a, b = {'pending_uploads': [first]}, {'pending_uploads': [second]}
    assert merge_state(a, b)['pending_uploads'] == [first]
    assert merge_state(b, a)['pending_uploads'] == [second]
    completed = {'uploads': [dict(first, prehrajto_video_id=123)]}
    assert merge_state(a, completed)['pending_uploads'] == []
    assert merge_state(completed, a)['pending_uploads'] == []


def test_pending_episode_blocks_other_sources_and_aliases_across_all_selectors(tmp_path, monkeypatch):
    (tmp_path / 'state').mkdir()
    (tmp_path / 'state/uploaded-shard-0.json').write_text(json.dumps({'pending_uploads': [intent()]}))
    for module in [picker, preparation, manifest]:
        monkeypatch.setattr(module, 'REPO_ROOT', tmp_path)
    state = picker.load_state()
    alias = dict(episode_id=99, series_id=2, season=1, episode=1, candidates=[{'source_id': 88}])
    assert picker.pick_next(state, [alias]) is None
    assert preparation.uploaded_episode_exclusions() == ({1}, {(2, 1, 1)})
    ids, keys, _ = manifest.load_upload_state_exclusions()
    assert ids == {1} and keys == {(2, 1, 1)}


@pytest.fixture
def upload_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, 'STATE', tmp_path / 'state.json')
    monkeypatch.setattr(sync, 'TMP_DIR', tmp_path)
    monkeypatch.setattr(sync, 'log', lambda message: None)
    monkeypatch.setattr(sync, 'has_probable_czech', lambda *a, **kw: (True, 'CZ'))
    video = SimpleNamespace(url='https://cdn.test/media', res=720, label='720p')
    monkeypatch.setattr(sync, 'resolve_stream', lambda url: SimpleNamespace(videos=[video], name='Example.mp4'))
    monkeypatch.setattr(sync, 'head_size', lambda url: 400_000_000)
    def download(url, path, **kwargs):
        path.write_bytes(b'complete fixture')
        return 400_000_000
    monkeypatch.setattr(sync, 'download_to', download)
    monkeypatch.setattr(sync, 'whisper_language', lambda path: ('cs', .99, 'ok'))
    episode = dict(episode_id=1, series_id=2, series_title='Example', season=1, episode=1,
                   display_name='Example S01E01 CZ Dabing')
    return episode, dict(source_id=7, url='https://prehraj.to/example/id'), {}


def test_failed_reservation_never_uploads_and_cleans_download(upload_fixture, monkeypatch, tmp_path):
    episode, candidate, state = upload_fixture
    def fail(reason):
        raise sync.StatePersistenceError('readonly storage')
    monkeypatch.setattr(sync, 'push_state', fail)
    monkeypatch.setattr(sync, 'upload_video', lambda *a, **kw: pytest.fail('Unreserved upload'))
    with pytest.raises(sync.StatePersistenceError):
        sync.try_candidate(episode, candidate, object(), state, allow_subtitles=True, description='')
    assert not list(tmp_path.glob('*.mp4'))
    assert not state.get('uploads')


def test_failed_final_checkpoint_retains_durable_reservation_until_reconciled(upload_fixture, monkeypatch):
    episode, candidate, state = upload_fixture
    remote = {}
    def checkpoint(reason):
        if reason.startswith('reserve '):
            remote.update(copy.deepcopy(state))
            return copy.deepcopy(state)
        raise sync.StatePersistenceError('checkpoint unavailable after upload')
    monkeypatch.setattr(sync, 'push_state', checkpoint)
    monkeypatch.setattr(sync, 'upload_video', lambda *a, **kw: 123)
    with pytest.raises(sync.StatePersistenceError):
        sync.try_candidate(episode, candidate, object(), state, allow_subtitles=True, description='')
    assert remote['pending_uploads'] and not remote.get('uploads')
    assert state['uploads'][0]['prehrajto_video_id'] == 123
    assert picker.pick_next(remote, [dict(episode, candidates=[candidate])]) is None
    recovered = merge_state(remote, state)
    assert recovered['pending_uploads'] == []
    assert recovered['uploads'][0]['prehrajto_video_id'] == 123


def test_another_workers_reservation_prevents_duplicate_upload(upload_fixture, monkeypatch):
    episode, candidate, state = upload_fixture
    monkeypatch.setattr(sync, 'push_state', lambda reason: {'pending_uploads': [intent()]})
    monkeypatch.setattr(sync, 'upload_video', lambda *a, **kw: pytest.fail('Duplicate upload'))
    assert not sync.try_candidate(episode, candidate, object(), state, allow_subtitles=True, description='')
    assert state['pending_uploads'][0]['intent_id'] == 'first'


def test_git_push_failure_is_fatal_and_preserves_checkpoint_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv('CI', 'true')
    monkeypatch.setattr(sync, 'REPO_ROOT', tmp_path)
    path = tmp_path / 'state/uploaded-shard-0.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'pending_uploads': [intent()]}))
    monkeypatch.setattr(sync, 'STATE', path)
    monkeypatch.setattr(sync, 'load_state', lambda: json.loads(path.read_text()))
    monkeypatch.setattr(sync.time, 'sleep', lambda seconds: None)
    pushes = []
    def run(args, **kwargs):
        if args[1] == 'push': pushes.append(args)
        return SimpleNamespace(returncode=1 if args[1] in {'push', 'diff'} else 0)
    monkeypatch.setattr(sync.subprocess, 'run', run)
    with pytest.raises(sync.StatePersistenceError): sync.push_state('reserve fixture')
    assert len(pushes) == 5
    snapshots = list((tmp_path / '.upload-checkpoints').glob('*.json'))
    assert len(snapshots) == 1
    assert json.loads(snapshots[0].read_text())['pending_uploads'] == [intent()]


def test_checkpoint_claim_checks_other_accounts_before_publishing(tmp_path, monkeypatch):
    monkeypatch.setenv('CI', 'true')
    monkeypatch.setattr(sync, 'REPO_ROOT', tmp_path)
    path = tmp_path / 'state/uploaded-shard-0.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'pending_uploads': [intent('ours')]}))
    monkeypatch.setattr(sync, 'STATE', path)
    other = dict(intent('other'), upload_account='serialy')
    monkeypatch.setattr(sync, 'load_state', lambda: {'pending_uploads': [other]})
    monkeypatch.setattr(sync.subprocess, 'run', lambda args, **kw: SimpleNamespace(returncode=1 if args[1]=='diff' else 0))
    remote = sync.push_state('reserve fixture')
    assert remote['pending_uploads'] == [other]
    assert json.loads(path.read_text())['pending_uploads'] == []
