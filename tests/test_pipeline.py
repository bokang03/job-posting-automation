from src.config import CareerSpec, Config, KeywordSpec, Profile, Settings
from src.models import JobPosting
from src.pipeline import run
from src.state import SeenStore


def posting(job_id, title="백엔드 개발자", source="jumpit", **overrides) -> JobPosting:
    base = dict(
        source=source,
        job_id=job_id,
        title=title,
        company="회사",
        url=f"https://example.com/{job_id}",
        tech_stacks=(),
        category="",
        career_min=0,
        career_max=0,
        location="서울",
        deadline="",
    )
    base.update(overrides)
    return JobPosting(**base)


def profile(name="백엔드 신입", sources=("jumpit",), **overrides) -> Profile:
    base = dict(
        name=name,
        enabled=True,
        sources=sources,
        keywords=KeywordSpec(any=("백엔드",), all=(), none=()),
        career=CareerSpec(min_years=0, max_years=0, include_irrelevant=True),
        locations=(),
        include_companies=(),
        exclude_companies=(),
        search_queries=(),
        search_companies=False,
        webhook_env="DISCORD_WEBHOOK_URL",
    )
    base.update(overrides)
    return Profile(**base)


def config(profiles, **settings) -> Config:
    return Config(settings=Settings(**settings), profiles=tuple(profiles))


class FakeSource:
    def __init__(self, name, postings=None, error=None):
        self.name = name
        self._postings = postings or []
        self._error = error
        self.fetch_count = 0

    def fetch(self, queries, max_pages):
        self.fetch_count += 1
        if self._error:
            raise self._error
        return list(self._postings)


class FakeNotifier:
    def __init__(self):
        self.sends = []

    def send(self, postings, profile_name):
        self.sends.append((profile_name, list(postings)))
        return len(postings)

    @property
    def all_sent(self):
        return [p for _, batch in self.sends for p in batch]


def run_with(cfg, sources, store, dry_run=False):
    notifier = FakeNotifier()
    report = run(cfg, sources, lambda _profile: notifier, store, dry_run=dry_run)
    return notifier, report


# --- 기본 동작 -------------------------------------------------------------


def test_matching_postings_are_sent(tmp_path):
    src = FakeSource("jumpit", [posting("1"), posting("2")])
    store = SeenStore(tmp_path / "seen.json")
    store.load()
    store.mark("초기화용")  # 첫 실행이 아니게 만든다
    store.save()
    store = SeenStore(tmp_path / "seen.json")
    store.load()

    notifier, report = run_with(config([profile()]), {"jumpit": src}, store)
    assert [p.job_id for p in notifier.all_sent] == ["1", "2"]
    assert report.total_sent == 2


def test_non_matching_postings_are_not_sent(tmp_path):
    src = FakeSource("jumpit", [posting("1", title="iOS 개발자")])
    store = SeenStore(tmp_path / "seen.json")
    store.load()
    store.mark("초기화용")
    store.save()
    store = SeenStore(tmp_path / "seen.json")
    store.load()

    notifier, _ = run_with(config([profile()]), {"jumpit": src}, store)
    assert notifier.all_sent == []


def test_disabled_profile_is_skipped(tmp_path):
    src = FakeSource("jumpit", [posting("1")])
    store = SeenStore(tmp_path / "seen.json")
    store.load()
    notifier, _ = run_with(config([profile(enabled=False)]), {"jumpit": src}, store)
    assert notifier.all_sent == []


# --- 중복 방지 -------------------------------------------------------------


def test_already_seen_posting_is_not_sent_again(tmp_path):
    src = FakeSource("jumpit", [posting("1"), posting("2")])
    store = SeenStore(tmp_path / "seen.json")
    store.load()
    store.mark("jumpit:1")
    store.save()
    store = SeenStore(tmp_path / "seen.json")
    store.load()

    notifier, _ = run_with(config([profile()]), {"jumpit": src}, store)
    assert [p.job_id for p in notifier.all_sent] == ["2"]


def test_sent_postings_are_remembered_for_the_next_run(tmp_path):
    path = tmp_path / "seen.json"
    src = FakeSource("jumpit", [posting("1")])

    store = SeenStore(path)
    store.load()
    store.mark("초기화용")
    store.save()
    store = SeenStore(path)
    store.load()
    run_with(config([profile()]), {"jumpit": src}, store)

    store2 = SeenStore(path)
    store2.load()
    notifier, _ = run_with(config([profile()]), {"jumpit": FakeSource("jumpit", [posting("1")])}, store2)
    assert notifier.all_sent == []


def test_same_posting_is_not_sent_twice_across_overlapping_profiles(tmp_path):
    src = FakeSource("jumpit", [posting("1")])
    store = SeenStore(tmp_path / "seen.json")
    store.load()
    store.mark("초기화용")
    store.save()
    store = SeenStore(tmp_path / "seen.json")
    store.load()

    profiles = [profile(name="A"), profile(name="B")]
    notifier, _ = run_with(config(profiles), {"jumpit": src}, store)
    assert len(notifier.all_sent) == 1


# --- 첫 실행 / 상한 --------------------------------------------------------


def test_first_run_sends_only_the_configured_number(tmp_path):
    postings = [posting(str(i)) for i in range(30)]
    store = SeenStore(tmp_path / "seen.json")
    store.load()
    assert store.is_first_run

    notifier, _ = run_with(
        config([profile()], first_run_limit=5), {"jumpit": FakeSource("jumpit", postings)}, store
    )
    assert len(notifier.all_sent) == 5


def test_first_run_marks_the_rest_as_seen_so_they_never_arrive_late(tmp_path):
    path = tmp_path / "seen.json"
    postings = [posting(str(i)) for i in range(30)]

    store = SeenStore(path)
    store.load()
    run_with(config([profile()], first_run_limit=5), {"jumpit": FakeSource("jumpit", postings)}, store)

    store2 = SeenStore(path)
    store2.load()
    notifier, _ = run_with(
        config([profile()]), {"jumpit": FakeSource("jumpit", postings)}, store2
    )
    assert notifier.all_sent == []


def test_run_is_capped_at_max_notifications(tmp_path):
    path = tmp_path / "seen.json"
    postings = [posting(str(i)) for i in range(30)]

    store = SeenStore(path)
    store.load()
    store.mark("초기화용")
    store.save()
    store = SeenStore(path)
    store.load()

    notifier, _ = run_with(
        config([profile()], max_notifications_per_run=8), {"jumpit": FakeSource("jumpit", postings)}, store
    )
    assert len(notifier.all_sent) == 8


def test_postings_over_the_cap_arrive_on_the_following_run(tmp_path):
    path = tmp_path / "seen.json"
    postings = [posting(str(i)) for i in range(12)]

    store = SeenStore(path)
    store.load()
    store.mark("초기화용")
    store.save()
    store = SeenStore(path)
    store.load()
    run_with(config([profile()], max_notifications_per_run=8), {"jumpit": FakeSource("jumpit", postings)}, store)

    store2 = SeenStore(path)
    store2.load()
    notifier, _ = run_with(
        config([profile()], max_notifications_per_run=8), {"jumpit": FakeSource("jumpit", postings)}, store2
    )
    assert len(notifier.all_sent) == 4


# --- 장애 격리 -------------------------------------------------------------


def test_failing_source_does_not_stop_the_others(tmp_path):
    broken = FakeSource("jobkorea", error=RuntimeError("사이트 개편으로 파싱 실패"))
    working = FakeSource("jumpit", [posting("1")])
    store = SeenStore(tmp_path / "seen.json")
    store.load()
    store.mark("초기화용")
    store.save()
    store = SeenStore(tmp_path / "seen.json")
    store.load()

    notifier, report = run_with(
        config([profile(sources=("jumpit", "jobkorea"))]),
        {"jumpit": working, "jobkorea": broken},
        store,
    )
    assert [p.job_id for p in notifier.all_sent] == ["1"]
    assert "jobkorea" in report.failed_sources


def test_source_used_by_two_profiles_is_fetched_only_once(tmp_path):
    src = FakeSource("jumpit", [posting("1")])
    store = SeenStore(tmp_path / "seen.json")
    store.load()
    run_with(config([profile(name="A"), profile(name="B")]), {"jumpit": src}, store)
    assert src.fetch_count == 1


# --- 미리보기 --------------------------------------------------------------


def test_dry_run_sends_nothing_and_leaves_state_untouched(tmp_path):
    path = tmp_path / "seen.json"
    src = FakeSource("jumpit", [posting("1")])
    store = SeenStore(path)
    store.load()

    notifier, report = run_with(config([profile()]), {"jumpit": src}, store, dry_run=True)
    assert notifier.sends == []
    assert not path.exists()
    assert report.matched_by_profile["백엔드 신입"] == 1
