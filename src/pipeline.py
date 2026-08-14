"""수집 -> 필터 -> 중복 제거 -> 알림 으로 이어지는 실행 흐름.

네트워크와 디스코드는 바깥에서 주입받으므로 이 파일은 테스트로 전부 검증할 수 있다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Config, Profile
from .filters import matches_profile
from .models import JobPosting
from .state import SeenStore

log = logging.getLogger(__name__)


@dataclass
class RunReport:
    fetched_by_source: dict[str, int] = field(default_factory=dict)
    matched_by_profile: dict[str, int] = field(default_factory=dict)
    sent_by_profile: dict[str, int] = field(default_factory=dict)
    failed_sources: dict[str, str] = field(default_factory=dict)
    first_run: bool = False
    dry_run: bool = False

    @property
    def total_sent(self) -> int:
        return sum(self.sent_by_profile.values())

    @property
    def total_matched(self) -> int:
        return sum(self.matched_by_profile.values())


def _queries_for(config: Config) -> tuple[str, ...]:
    """검색어 기반 사이트에 넘길 단어. 모든 활성 프로필의 검색어를 합친다."""
    out: list[str] = []
    for profile in config.active_profiles:
        for q in profile.effective_queries():
            if q not in out:
                out.append(q)
    return tuple(out)


def gather(config: Config, sources: dict, report: RunReport) -> dict[str, list[JobPosting]]:
    """소스별로 공고를 모은다. 한 소스가 실패해도 나머지는 계속 진행한다."""
    needed = {name for profile in config.active_profiles for name in profile.sources}
    queries = _queries_for(config)

    collected: dict[str, list[JobPosting]] = {}
    for name in sorted(needed):
        source = sources.get(name)
        if source is None:
            report.failed_sources[name] = "등록되지 않은 사이트"
            continue
        try:
            postings = source.fetch(queries, config.settings.max_pages)
        except Exception as e:
            log.warning("[%s] 수집 실패: %s", name, e)
            report.failed_sources[name] = str(e)
            collected[name] = []
            continue
        collected[name] = postings
        report.fetched_by_source[name] = len(postings)
        log.info("[%s] %d건 수집", name, len(postings))
    return collected


def _candidates(profile: Profile, collected: dict[str, list[JobPosting]]) -> list[JobPosting]:
    out: list[JobPosting] = []
    for name in profile.sources:
        for posting in collected.get(name, []):
            if matches_profile(posting, profile):
                out.append(posting)
    return out


class _Budget:
    """이번 실행에서 상세 조회를 몇 건까지 더 할 수 있는지 세는 카운터."""

    def __init__(self, limit: int):
        self.left = limit

    def take(self, count: int) -> int:
        allowed = max(0, min(count, self.left))
        self.left -= allowed
        return allowed


def _enrich(postings, sources: dict, config: Config, budget: _Budget, report: RunReport, profile: Profile):
    """소스별로 묶어서 추가 정보를 채운다.

    조건을 통과했고 아직 안 보낸 공고만 들어오므로, 평소에는 몇 건 되지 않는다.
    설정을 크게 바꿔 후보가 갑자기 불어나는 경우를 대비해 상한을 둔다.
    보강한 뒤에는 새로 알게 된 정보(고용형태 등)로 조건을 한 번 더 확인한다.
    """
    by_source: dict[str, list] = {}
    for p in postings:
        by_source.setdefault(p.source, []).append(p)

    enriched: dict[str, JobPosting] = {}
    for name, group in by_source.items():
        source = sources.get(name)
        if source is None or not hasattr(source, "enrich"):
            continue
        allowed = budget.take(len(group))
        if allowed <= 0:
            continue
        try:
            for p in source.enrich(group[:allowed]):
                enriched[p.uid] = p
        except Exception as e:
            log.warning("[%s] 상세 조회 실패: %s", name, e)
            report.failed_sources.setdefault(name, f"상세 조회 실패: {e}")

    out = []
    for p in postings:
        p = enriched.get(p.uid, p)
        # 보강으로 알게 된 값 때문에 조건에서 빠질 수 있다 (예: 고용형태가 연수생)
        if p.uid in enriched and not matches_profile(p, profile):
            log.info("  보강 후 제외: %s | %s (%s)", p.company, p.title, ", ".join(p.tags))
            continue
        out.append(p)
    return out


def run(
    config: Config,
    sources: dict,
    notifier_for,
    store: SeenStore,
    dry_run: bool = False,
) -> RunReport:
    report = RunReport(first_run=store.is_first_run, dry_run=dry_run)
    collected = gather(config, sources, report)

    first_run = store.is_first_run
    limit = config.settings.first_run_limit if first_run else config.settings.max_notifications_per_run
    budget = limit
    enrich_budget = _Budget(config.settings.max_enrich_per_run)

    for profile in config.active_profiles:
        matched = _candidates(profile, collected)
        report.matched_by_profile[profile.name] = len(matched)

        fresh = [p for p in matched if not store.has_seen(p.uid)]
        if dry_run:
            report.sent_by_profile[profile.name] = 0
            continue

        fresh = _enrich(fresh, sources, config, enrich_budget, report, profile)

        to_send = fresh[:budget] if budget > 0 else []

        if to_send:
            notifier = notifier_for(profile)
            sent_count = notifier.send(to_send, profile.name)
            for posting in to_send[:sent_count]:
                store.mark(posting.uid)
            report.sent_by_profile[profile.name] = sent_count
            budget -= sent_count
        else:
            report.sent_by_profile[profile.name] = 0

        if first_run:
            # 첫 실행에서는 남은 과거 공고를 '이미 본 것'으로 처리한다.
            # 그러지 않으면 다음 실행부터 수백 건이 뒤늦게 쏟아진다.
            for posting in fresh:
                store.mark(posting.uid)

    if not dry_run:
        store.save()

    return report
