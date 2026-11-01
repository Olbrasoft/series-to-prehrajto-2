from __future__ import annotations

from src.upload_state_merge import merge_state


def test_merge_preserves_new_upload_and_description_metadata() -> None:
    current = {
        "schema_version": 1,
        "last_updated": "2026-07-05T20:22:52Z",
        "uploads": [
            {
                "episode_id": 1,
                "series_id": 10,
                "season": 1,
                "episode": 1,
                "display_name": "Series S01E01",
                "prehrajto_video_id": 1001,
                "description_updated_at": "2026-07-05T20:10:00Z",
                "description_source": "gemma_prepared",
                "description_text_hash": "abc",
            },
            {
                "episode_id": 2,
                "series_id": 10,
                "season": 1,
                "episode": 2,
                "display_name": "Series S01E02",
                "prehrajto_video_id": 1002,
            },
        ],
        "failed_attempts": [],
    }
    incoming = {
        "schema_version": 1,
        "last_updated": "2026-07-05T20:30:00Z",
        "uploads": [
            {
                "episode_id": 1,
                "series_id": 10,
                "season": 1,
                "episode": 1,
                "display_name": "Series S01E01",
                "prehrajto_video_id": 1001,
            }
        ],
        "failed_attempts": [
            {
                "episode_id": 3,
                "source_id": 3003,
                "reason": "download_failed: timeout",
                "permanent": False,
            }
        ],
    }

    merged = merge_state(current, incoming)

    assert [upload["episode_id"] for upload in merged["uploads"]] == [1, 2]
    assert merged["uploads"][0]["description_updated_at"] == "2026-07-05T20:10:00Z"
    assert merged["uploads"][0]["description_source"] == "gemma_prepared"
    assert merged["failed_attempts"][0]["source_id"] == 3003
    assert merged["last_updated"] == "2026-07-05T20:30:00Z"


def test_merge_can_filter_uploads_by_account() -> None:
    current = {
        "schema_version": 1,
        "uploads": [
            {
                "episode_id": 1,
                "series_id": 10,
                "season": 1,
                "episode": 1,
                "upload_account": "primary",
            },
            {
                "episode_id": 2,
                "series_id": 10,
                "season": 1,
                "episode": 2,
                "upload_account": "serialy",
            },
        ],
        "failed_attempts": [],
    }
    incoming = {
        "schema_version": 1,
        "uploads": [
            {
                "episode_id": 3,
                "series_id": 10,
                "season": 1,
                "episode": 3,
                "upload_account": "primary",
            },
            {
                "episode_id": 4,
                "series_id": 10,
                "season": 1,
                "episode": 4,
                "upload_account": "serialy",
            },
        ],
        "failed_attempts": [],
    }

    merged = merge_state(current, incoming, upload_account="serialy")

    assert [upload["episode_id"] for upload in merged["uploads"]] == [2, 4]
    assert all(upload["upload_account"] == "serialy" for upload in merged["uploads"])


def test_state_merge_and_save_remove_credentials_from_old_failures(tmp_path):
    import json
    from src.upload_state_merge import save_state
    source = {'uploads': [{'episode_id': 12, 'prehrajto_video_id': 34}], 'failed_attempts': [
        {'episode_id': 56, 'source_id': 78, 'reason': 'HTTP error https://proxy.invalid/?key=private-proxy-value&url=episode'}]}
    sanitized = merge_state({}, source)
    assert sanitized['uploads'] == source['uploads']
    assert 'private-proxy-value' not in json.dumps(sanitized)
    assert 'private-proxy-value' in source['failed_attempts'][0]['reason']
    # An older worker must not reintroduce the secret or duplicate its failure.
    assert len(merge_state(sanitized, source)['failed_attempts']) == 1
    path = tmp_path / 'state.json'
    save_state(path, source)
    assert 'private-proxy-value' not in path.read_text()
    assert json.loads(path.read_text())['uploads'] == source['uploads']


def test_state_redaction_covers_encoded_urls_and_preserves_episode_identity():
    from src.diagnostic_redaction import redact_diagnostics
    source = {'episode_id': 12, 'source_url': 'https://prehraj.to/episode/abcdef123456',
              'error': 'https://proxy.invalid/?key=hidden-value&url=https%3A%2F%2Fproxy.invalid%2F%3Fkey%3Dnested-value%26url%3Depisode',
              'details': ['https://user:private-password@proxy.invalid/path']}
    cleaned = redact_diagnostics(source)
    assert cleaned['episode_id'] == 12
    assert cleaned['source_url'] == source['source_url']
    for secret in ['hidden-value', 'nested-value', 'private-password']:
        assert secret not in str(cleaned)
    assert redact_diagnostics(cleaned) == cleaned
