"""Exercise checkpoint races against real Git repositories and remote refs."""

import json
import subprocess
import sys

import pytest

from src import sync_batch as sync
from src import pick_next_episode as picker


REAL_RUN = subprocess.run


def git(directory, *args):
    return REAL_RUN(['git', *args], cwd=directory, check=True,
                    capture_output=True, text=True).stdout.strip()


def reservation(identifier, account='primary'):
    return dict(intent_id=identifier, episode_id=1, series_id=2, season=1,
                episode=1, upload_account=account, started_at='2026-11-02T16:00:00Z')


@pytest.fixture
def repositories(tmp_path, monkeypatch):
    remote, worker, other = [tmp_path / name for name in ('remote.git', 'worker', 'other')]
    git(tmp_path, 'init', '--bare', '--initial-branch=main', str(remote))
    git(tmp_path, 'clone', str(remote), str(worker))
    git(worker, 'config', 'user.name', 'Checkpoint test')
    git(worker, 'config', 'user.email', 'checkpoint@example.test')
    (worker / 'state').mkdir()
    empty = dict(schema_version=1, uploads=[], failed_attempts=[], pending_uploads=[])
    for shard in (0, 2):
        (worker / f'state/uploaded-shard-{shard}.json').write_text(json.dumps(empty))
    git(worker, 'add', '.')
    git(worker, 'commit', '-m', 'Seed upload state')
    git(worker, 'push', 'origin', 'main')
    git(tmp_path, 'clone', str(remote), str(other))
    git(other, 'config', 'user.name', 'Concurrent writer')
    git(other, 'config', 'user.email', 'writer@example.test')
    monkeypatch.chdir(worker)
    monkeypatch.setenv('CI', 'true')
    monkeypatch.setattr(sync, 'REPO_ROOT', worker)
    monkeypatch.setattr(sync, 'STATE', worker / 'state/uploaded-shard-0.json')
    monkeypatch.setattr(sync, 'SHARD_ID', 0)
    monkeypatch.setattr(sync, 'NUM_SHARDS', 4)
    monkeypatch.setattr(sync, 'UPLOAD_ACCOUNT', 'primary')
    monkeypatch.setattr(sync.time, 'sleep', lambda seconds: None)
    loads = []

    def load():
        loads.append(True)
        return picker._merge_states(sorted((worker / 'state').glob('uploaded-shard-*.json')))

    monkeypatch.setattr(sync, 'load_state', load)
    sync.STATE.write_text(json.dumps(dict(empty, pending_uploads=[reservation('ours')])))
    return worker, other, loads


def publish_other(other, relative, value):
    git(other, 'fetch', 'origin', 'main')
    git(other, 'reset', '--hard', 'origin/main')
    path = other / relative
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value))
    git(other, 'add', relative)
    git(other, 'commit', '-m', 'Concurrent update')
    git(other, 'push', 'origin', 'HEAD:main')


def test_repeated_status_commits_rebase_without_remerging_upload_history(repositories, monkeypatch):
    worker, other, loads = repositories
    pushes = []

    def race(args, **kwargs):
        if args[1] == 'push':
            pushes.append(True)
            if len(pushes) <= 7:
                publish_other(other, 'reports/ops-status.json', {'revision': len(pushes)})
        return REAL_RUN(args, **kwargs)

    monkeypatch.setattr(sync.subprocess, 'run', race)
    result = sync.push_state('reserve fixture')
    assert len(pushes) == 8  # More conflicts than the former five-attempt limit.
    assert len(loads) == 1  # Reporting races do not repeat the expensive merge.
    assert result['pending_uploads'] == [reservation('ours')]
    remote_state = json.loads(git(worker, 'show', 'origin/main:state/uploaded-shard-0.json'))
    assert remote_state['pending_uploads'] == [reservation('ours')]
    assert json.loads(git(worker, 'show', 'origin/main:reports/ops-status.json')) == {'revision': 7}
    assert not list((worker / '.upload-checkpoints').glob('*.json'))


def test_other_account_claim_after_rebase_forces_full_global_recheck(repositories, monkeypatch):
    worker, other, loads = repositories
    pushes = []
    committed = reservation('winner', account='serialy')

    def race(args, **kwargs):
        if args[1] == 'push':
            pushes.append(True)
            if len(pushes) == 1:
                publish_other(other, 'reports/ops-status.json', {'revision': 1})
            elif len(pushes) == 2:
                publish_other(other, 'state/uploaded-shard-2.json', dict(
                    schema_version=1, uploads=[], failed_attempts=[], pending_uploads=[committed]))
        return REAL_RUN(args, **kwargs)

    monkeypatch.setattr(sync.subprocess, 'run', race)
    result = sync.push_state('reserve fixture')
    assert len(loads) == 2
    assert result['pending_uploads'] == [committed]
    assert json.loads(git(worker, 'show', 'origin/main:state/uploaded-shard-0.json'))['pending_uploads'] == []
    assert json.loads(git(worker, 'show', 'origin/main:state/uploaded-shard-2.json'))['pending_uploads'] == [committed]


def test_checkpoint_only_requires_no_portal_credentials_or_upload(monkeypatch):
    monkeypatch.delenv('PREHRAJTO_EMAIL', raising=False)
    monkeypatch.delenv('PREHRAJTO_PASSWORD', raising=False)
    monkeypatch.setattr(sys, 'argv', ['sync_batch.py', '--checkpoint-only'])
    calls = []
    monkeypatch.setattr(sync, 'push_state', lambda reason: calls.append(reason))
    monkeypatch.setattr(sync, 'login', lambda *args: pytest.fail('Unexpected portal login'))
    monkeypatch.setattr(sync, 'load_backlog', lambda: pytest.fail('Unexpected upload selection'))
    assert sync.main() == 0
    assert calls == ['persist final upload state']
