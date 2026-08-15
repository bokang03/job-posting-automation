"""알림 직전에 상세 정보를 채워 넣는 보강 단계 테스트.

잡코리아는 고용형태를 검색 목록에 주지 않아 상세 페이지를 봐야 한다.
모든 공고에 대해 상세 페이지를 열면 요청이 너무 많아지므로,
'조건을 통과했고 아직 안 보낸' 공고에 대해서만 연다.
"""

from src.config import CareerSpec, Config, KeywordSpec, Profile, Settings
from src.models import JobPosting
from src.pipeline import run
from src.state import SeenStore


def posting(job_id, source="jobkorea", title="백엔드 개발자", **overrides) -> JobPosting:
    base = dict(
        source=source,
        job_id=job_id,
        title=title,
        company="회사",
        url=f"https://example.com/{job_id}",
        tech_stacks=(),
        category="",
        tags=(),
        career_min=0,
        career_max=0,
        location="서울",
        deadline="",
    )
    base.update(overrides)
    return JobPosting(**base)


def profile(**overrides) -> Profile:
    base = dict(
        name="테스트",
        enabled=True,
        sources=("jobkorea",),
        keywords=KeywordSpec(any=("백엔드",), all=(), none=("연수생", "교육생")),
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


class FakeJobKorea:
    """고용형태를 미리 정해둔 가짜 잡코리아 소스."""

    name = "jobkorea"

    def __init__(self, postings, employment_by_id=None, fail_ids=()):
        self._postings = postings
        self._employment = employment_by_id or {}
        self._fail_ids = set(fail_ids)
        self.enriched_ids = []

    def fetch(self, queries, max_pages):
        return list(self._postings)

    def enrich(self, postings):
        out = []
        for p in postings:
            self.enriched_ids.append(p.job_id)
            if p.job_id in self._fail_ids:
                out.append(p)
                continue
            label = self._employment.get(p.job_id)
            out.append(p if label is None else p.with_tags((label,)))
        return out


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, postings, profile_name):
        self.sent.extend(postings)
        return len(postings)


def run_with(sources, store, profiles=None, **settings):
    cfg = Config(settings=Settings(**settings), profiles=tuple(profiles or [profile()]))
    notifier = FakeNotifier()
    report = run(cfg, sources, lambda _p: notifier, store, dry_run=False)
    return notifier, report


def ready_store(tmp_path):
    """첫 실행 제한에 걸리지 않도록 기록이 있는 상태로 만든다."""
    path = tmp_path / "seen.json"
    store = SeenStore(path)
    store.load()
    store.mark("초기화용")
    store.save()
    store = SeenStore(path)
    store.load()
    return store


def test_posting_excluded_by_employment_type_is_not_sent(tmp_path):
    src = FakeJobKorea([posting("1")], employment_by_id={"1": "연수생/교육생"})
    notifier, _ = run_with({"jobkorea": src}, ready_store(tmp_path))
    assert notifier.sent == []


def test_posting_with_acceptable_employment_type_is_sent(tmp_path):
    src = FakeJobKorea([posting("1")], employment_by_id={"1": "정규직"})
    notifier, _ = run_with({"jobkorea": src}, ready_store(tmp_path))
    assert [p.job_id for p in notifier.sent] == ["1"]


def test_employment_type_is_kept_on_the_posting_for_the_notification(tmp_path):
    src = FakeJobKorea([posting("1")], employment_by_id={"1": "정규직"})
    notifier, _ = run_with({"jobkorea": src}, ready_store(tmp_path))
    assert "정규직" in notifier.sent[0].tags


def test_only_postings_that_passed_the_filter_are_enriched(tmp_path):
    """조건에 안 맞는 공고까지 상세 페이지를 열면 요청 낭비다."""
    src = FakeJobKorea([posting("1"), posting("2", title="iOS 개발자")])
    run_with({"jobkorea": src}, ready_store(tmp_path))
    assert src.enriched_ids == ["1"]


def test_already_seen_postings_are_not_enriched(tmp_path):
    path = tmp_path / "seen.json"
    store = SeenStore(path)
    store.load()
    store.mark("jobkorea:1")
    store.save()
    store = SeenStore(path)
    store.load()

    src = FakeJobKorea([posting("1"), posting("2")])
    run_with({"jobkorea": src}, store)
    assert src.enriched_ids == ["2"]


def test_posting_is_kept_when_the_detail_page_cannot_be_read(tmp_path):
    """상세 조회에 실패했다고 공고를 버리면 진짜 기회를 놓친다."""
    src = FakeJobKorea([posting("1")], fail_ids=["1"])
    notifier, _ = run_with({"jobkorea": src}, ready_store(tmp_path))
    assert [p.job_id for p in notifier.sent] == ["1"]


def test_enrichment_is_capped_so_a_config_change_cannot_flood_requests(tmp_path):
    src = FakeJobKorea([posting(str(i)) for i in range(50)])
    run_with({"jobkorea": src}, ready_store(tmp_path), max_enrich_per_run=5)
    assert len(src.enriched_ids) == 5


def test_postings_beyond_the_enrichment_cap_are_still_sent(tmp_path):
    src = FakeJobKorea([posting(str(i)) for i in range(8)])
    notifier, _ = run_with({"jobkorea": src}, ready_store(tmp_path), max_enrich_per_run=3)
    assert len(notifier.sent) == 8


def test_source_without_enrich_support_still_works(tmp_path):
    class Plain:
        name = "jumpit"

        def fetch(self, queries, max_pages):
            return [posting("1", source="jumpit")]

    notifier, _ = run_with(
        {"jumpit": Plain()}, ready_store(tmp_path), profiles=[profile(sources=("jumpit",))]
    )
    assert len(notifier.sent) == 1
