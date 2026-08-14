import json
from datetime import datetime, timedelta, timezone

from src.state import SeenStore


def test_new_store_reports_first_run(tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    store.load()
    assert store.is_first_run


def test_store_with_existing_records_is_not_first_run(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text(json.dumps({"jumpit:1": "2026-08-01T00:00:00+00:00"}), encoding="utf-8")
    store = SeenStore(path)
    store.load()
    assert not store.is_first_run


def test_unseen_uid_reported_as_new(tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    store.load()
    assert not store.has_seen("jumpit:1")


def test_marked_uid_is_remembered_after_save_and_reload(tmp_path):
    path = tmp_path / "seen.json"
    store = SeenStore(path)
    store.load()
    store.mark("jumpit:1")
    store.save()

    reloaded = SeenStore(path)
    reloaded.load()
    assert reloaded.has_seen("jumpit:1")


def test_save_creates_parent_directory(tmp_path):
    store = SeenStore(tmp_path / "nested" / "dir" / "seen.json")
    store.load()
    store.mark("jumpit:1")
    store.save()
    assert (tmp_path / "nested" / "dir" / "seen.json").exists()


def test_entries_older_than_retention_are_pruned_on_save(tmp_path):
    path = tmp_path / "seen.json"
    old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    path.write_text(json.dumps({"jumpit:old": old, "jumpit:recent": recent}), encoding="utf-8")

    store = SeenStore(path, retention_days=60)
    store.load()
    store.save()

    data = json.loads(path.read_text(encoding="utf-8"))
    assert "jumpit:old" not in data
    assert "jumpit:recent" in data


def test_corrupted_state_file_is_treated_as_empty(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text("{{{ 깨진 파일", encoding="utf-8")
    store = SeenStore(path)
    store.load()
    assert store.is_first_run
    assert not store.has_seen("jumpit:1")


def test_entry_with_unparseable_timestamp_is_dropped_on_save(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text(json.dumps({"jumpit:1": "어제쯤?"}), encoding="utf-8")
    store = SeenStore(path, retention_days=60)
    store.load()
    store.save()
    assert "jumpit:1" not in json.loads(path.read_text(encoding="utf-8"))
