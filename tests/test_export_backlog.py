import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from src.export_backlog import write_backlog


def test_identical_exports_have_identical_bytes_and_keep_unicode(tmp_path):
    rows = [{'episode_id': 1, 'series_title': 'Český seriál'}]
    first, second = tmp_path / 'first.gz', tmp_path / 'second.gz'
    write_backlog(first, rows)
    write_backlog(second, rows)
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes()[4:8] == b'\0\0\0\0'
    with gzip.open(first, 'rt') as fh:
        assert [json.loads(line) for line in fh] == rows


def test_plain_export_remains_readable(tmp_path):
    path = tmp_path / 'backlog.jsonl'
    write_backlog(path, [{'episode_id': 1}])
    assert json.loads(path.read_text()) == {'episode_id': 1}
