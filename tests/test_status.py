"""새 공고가 없어도 시스템이 살아있는지 알려주는 상태 메시지.

매 실행마다 보내면 하루 48번이라 알림 채널이 못 쓰게 된다.
그래서 '조용한 상태가 일정 시간 이어질 때만' 한 번 보낸다.
"""

from datetime import datetime, timedelta, timezone

from src.status import StatusStore

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def store_at(tmp_path, last_sent=None) -> StatusStore:
    s = StatusStore(tmp_path / "status.json")
    s.load()
    if last_sent is not None:
        s.mark_sent(last_sent)
        s.save()
        s = StatusStore(tmp_path / "status.json")
        s.load()
    return s


def should(store, *, sent=0, failures=False, hours=6, now=NOW):
    return store.should_send(sent_count=sent, has_failures=failures, heartbeat_hours=hours, now=now)


# --- 보내지 않아야 하는 경우 ---------------------------------------------


def test_no_status_when_alerts_were_sent(tmp_path):
    """공고 알림이 갔다면 그것으로 살아있음이 증명된다."""
    assert not should(store_at(tmp_path, NOW - timedelta(days=1)), sent=3)


def test_no_status_before_the_interval_has_passed(tmp_path):
    assert not should(store_at(tmp_path, NOW - timedelta(hours=2)), hours=6)


def test_heartbeat_can_be_turned_off(tmp_path):
    assert not should(store_at(tmp_path, NOW - timedelta(days=7)), hours=0)


# --- 보내야 하는 경우 -----------------------------------------------------


def test_status_sent_on_the_very_first_run(tmp_path):
    """설정이 제대로 됐는지 처음 한 번은 알려준다."""
    assert should(store_at(tmp_path))


def test_status_sent_once_the_interval_has_passed(tmp_path):
    assert should(store_at(tmp_path, NOW - timedelta(hours=6, minutes=1)), hours=6)


def test_failure_shortens_the_wait_to_one_hour(tmp_path):
    """사이트가 막힌 건 손을 봐야 하는 일이라 더 빨리 알린다."""
    s = store_at(tmp_path, NOW - timedelta(hours=1, minutes=1))
    assert should(s, failures=True, hours=6)


def test_failure_still_respects_one_hour_spacing(tmp_path):
    """실패가 이어져도 30분마다 도배하지는 않는다."""
    s = store_at(tmp_path, NOW - timedelta(minutes=30))
    assert not should(s, failures=True, hours=6)


def test_failure_never_waits_longer_than_the_configured_interval(tmp_path):
    """주기를 30분으로 짧게 설정했다면 실패 알림도 그 주기를 따른다."""
    s = store_at(tmp_path, NOW - timedelta(minutes=40))
    assert should(s, failures=True, hours=0.5)


# --- 기록 -----------------------------------------------------------------


def test_sent_time_survives_a_reload(tmp_path):
    s = StatusStore(tmp_path / "status.json")
    s.load()
    s.mark_sent(NOW)
    s.save()

    again = StatusStore(tmp_path / "status.json")
    again.load()
    assert again.last_sent_at == NOW


def test_corrupted_status_file_is_treated_as_empty(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("{{{ 깨진 파일", encoding="utf-8")
    s = StatusStore(path)
    s.load()
    assert s.last_sent_at is None


def test_save_creates_the_parent_directory(tmp_path):
    s = StatusStore(tmp_path / "nested" / "status.json")
    s.load()
    s.mark_sent(NOW)
    s.save()
    assert (tmp_path / "nested" / "status.json").exists()
