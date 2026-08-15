"""파이프라인이 상태 메시지를 언제 실제로 보내는지 확인한다."""

from datetime import datetime, timedelta, timezone

from src.config import CareerSpec, Config, KeywordSpec, Profile, Settings
from src.models import JobPosting
from src.pipeline import run
from src.state import SeenStore
from src.status import StatusStore

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def posting(job_id, title="백엔드 개발자"):
    return JobPosting(
        source="jumpit", job_id=job_id, title=title, company="회사",
        url=f"https://x/{job_id}", career_min=0, career_max=0, location="서울",
    )


def profile():
    return Profile(
        name="테스트", enabled=True, sources=("jumpit",),
        keywords=KeywordSpec(any=("백엔드",), all=(), none=()),
        career=CareerSpec(0, 0, True), locations=(), include_companies=(),
        exclude_companies=(), search_queries=(), webhook_env="DISCORD_WEBHOOK_URL",
    )


class Src:
    name = "jumpit"

    def __init__(self, postings=None, error=None):
        self._postings = postings or []
        self._error = error

    def fetch(self, queries, max_pages):
        if self._error:
            raise self._error
        return list(self._postings)


class Notifier:
    def __init__(self):
        self.alerts = []
        self.statuses = []

    def send(self, postings, profile_name):
        self.alerts.extend(postings)
        return len(postings)

    def send_status(self, report):
        self.statuses.append(report)
        return True


def run_it(tmp_path, src, *, seeded=True, last_status=None, hours=6, now=NOW):
    seen = SeenStore(tmp_path / "seen.json")
    seen.load()
    if seeded:
        seen.mark("초기화용")
        seen.save()
        seen = SeenStore(tmp_path / "seen.json")
        seen.load()

    status = StatusStore(tmp_path / "status.json")
    status.load()
    if last_status is not None:
        status.mark_sent(last_status)
        status.save()
        status = StatusStore(tmp_path / "status.json")
        status.load()

    cfg = Config(settings=Settings(heartbeat_hours=hours), profiles=(profile(),))
    notifier = Notifier()
    report = run(cfg, {"jumpit": src}, lambda _p: notifier, seen, status=status, now=now)
    return notifier, report, status


def test_status_is_not_sent_when_alerts_went_out(tmp_path):
    notifier, _, _ = run_it(tmp_path, Src([posting("1")]), last_status=NOW - timedelta(days=1))
    assert len(notifier.alerts) == 1
    assert notifier.statuses == []


def test_status_is_sent_when_nothing_new_for_a_long_time(tmp_path):
    notifier, _, _ = run_it(tmp_path, Src([]), last_status=NOW - timedelta(hours=7))
    assert len(notifier.statuses) == 1


def test_status_is_not_sent_again_too_soon(tmp_path):
    notifier, _, _ = run_it(tmp_path, Src([]), last_status=NOW - timedelta(hours=1))
    assert notifier.statuses == []


def test_status_time_is_recorded_so_it_is_not_repeated(tmp_path):
    _, _, status = run_it(tmp_path, Src([]), last_status=NOW - timedelta(hours=7))
    assert status.last_sent_at == NOW


def test_failed_source_triggers_status_sooner(tmp_path):
    notifier, report, _ = run_it(
        tmp_path, Src(error=RuntimeError("차단됨")), last_status=NOW - timedelta(hours=2)
    )
    assert len(notifier.statuses) == 1
    assert "jumpit" in report.failed_sources


def test_heartbeat_can_be_disabled(tmp_path):
    notifier, _, _ = run_it(tmp_path, Src([]), last_status=NOW - timedelta(days=7), hours=0)
    assert notifier.statuses == []


def test_dry_run_never_sends_a_status_message(tmp_path):
    seen = SeenStore(tmp_path / "seen.json")
    seen.load()
    status = StatusStore(tmp_path / "status.json")
    status.load()
    cfg = Config(settings=Settings(heartbeat_hours=6), profiles=(profile(),))
    notifier = Notifier()
    run(cfg, {"jumpit": Src([])}, lambda _p: notifier, seen, dry_run=True, status=status, now=NOW)
    assert notifier.statuses == []


def test_pipeline_works_without_a_status_store(tmp_path):
    """상태 기능을 안 쓰는 호출도 그대로 동작해야 한다."""
    seen = SeenStore(tmp_path / "seen.json")
    seen.load()
    seen.mark("초기화용")
    seen.save()
    seen = SeenStore(tmp_path / "seen.json")
    seen.load()
    cfg = Config(settings=Settings(), profiles=(profile(),))
    notifier = Notifier()
    run(cfg, {"jumpit": Src([posting("1")])}, lambda _p: notifier, seen)
    assert len(notifier.alerts) == 1
