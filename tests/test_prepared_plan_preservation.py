"""Exercise empty-discovery races, retry pacing and the measured upload floor."""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import prepare_episode_sources as prep
import merge_preparation_results as merge
from source_quality import source_meets_size_requirement


def ready_plan():
    return dict(episode_id=12, series_id=1, series_slug="example", series_title="Example",
                season=1, episode=12, prepared_at="2026-11-12T01:00:00Z", upload_ready=True,
                needs_subtitles_after_upload=True, upload_kind="subtitles",
                tested_source_count=1, selected_source=dict(source_id=42, filesize_bytes=400 * 1024**2,
                verdict="CZ_SUBTITLES_ONLY", signals={"provider_probe": {
                    "status": "ok", "streams": [{"res": 480}], "stream_filesize_bytes": 400 * 1024**2}}))


@pytest.mark.parametrize("reverse", [False, True])
def test_empty_search_never_erases_verified_plan_in_either_merge_order(reverse):
    ready = ready_plan()
    empty = dict(ready, prepared_at="2026-11-12T02:00:00Z", upload_ready=False,
                 selected_source=None, tested_source_count=0, tested_sources=[])
    current, incoming = (empty, ready) if reverse else (ready, empty)
    result = merge.newer_prepared_wins(current, incoming)
    assert result["upload_ready"]
    assert result["selected_source"] == ready["selected_source"]
    assert result["prepared_at"] == ready["prepared_at"]  # Do not falsify evidence age.
    assert result["discovery_checked_at"] == empty["prepared_at"]
    assert merge.newer_prepared_wins(result, empty) == result


def test_actual_new_source_test_can_invalidate_an_old_selection():
    ready = ready_plan()
    negative = dict(ready, prepared_at="2026-11-12T02:00:00Z", upload_ready=False,
                    selected_source=None, tested_source_count=1)
    assert merge.newer_prepared_wins(ready, negative) == negative


def test_persisted_plan_resumes_after_cooldown_without_another_language_check(tmp_path):
    ready = ready_plan()
    path = tmp_path / "prepared.jsonl"
    prep.write_compacted_prepared(path, [ready])
    empty = dict(ready, prepared_at="2026-11-12T02:00:00Z", upload_ready=False,
                 selected_source=None, tested_source_count=0, tested_sources=[])
    effective = prep.write_compacted_prepared(path, [empty])
    assert effective[0]["upload_ready"]
    followup = tmp_path / "subtitles.jsonl"
    prep.update_subtitle_followup_queue(followup, effective)
    assert prep.load_jsonl(followup)[0]["source_id"] == 42
    assert not prep.latest_usable_prepared_episode_ids(path, {42})
    assert prep.latest_usable_prepared_episode_ids(path, set()) == {12}
    now = dt.datetime(2026, 11, 12, 3, tzinfo=dt.timezone.utc)
    assert not prep.retry_due(effective[0], now=now, unavailable_sources={42})
    assert prep.retry_due(effective[0], now=now + dt.timedelta(days=1), unavailable_sources={42})


@pytest.mark.parametrize("measured_mib,accepted", [(299, False), (300, True), (325, True)])
def test_sd_between_upload_floor_and_preference_margin_is_measured_before_acceptance(monkeypatch, measured_mib, accepted):
    episode = dict(episode_id=12, series_id=1, series_slug="example", series_title="Example",
                   season=1, episode=12)
    source = dict(episode, provider="prehrajto", source_id=42, source_url="https://prehraj.to/example/abcdef123456",
                  source_title="Example S01E12 CZ Dabing", filesize_bytes=325 * 1024**2)
    episode["sources"] = [source]
    calls = []
    original = prep.audit_one
    def audit(item, **kwargs):
        result = original(item, use_whisper=False, sample_seconds=20, probe_stream=False)
        if kwargs["probe_stream"]:
            calls.append(item["source_id"])
            result["filesize_bytes"] = measured_mib * 1024**2
            result["signals"]["provider_probe"] = dict(status="ok", streams=[dict(res=480)],
                                                       stream_filesize_bytes=measured_mib * 1024**2)
        return result
    monkeypatch.setattr(prep, "audit_one", audit)
    plan = prep.prepare_episode(episode, use_whisper=False, sample_seconds=20, source_limit=4,
                                burned=set(), require_resolvable_source=True, live_search=False,
                                live_search_limit=4, live_search_query_limit=4)
    assert calls == [42]
    assert plan["upload_ready"] is accepted
    if accepted:
        assert source_meets_size_requirement(plan["selected_source"])
