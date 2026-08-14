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

    for profile in config.active_profiles:
        matched = _candidates(profile, collected)
        report.matched_by_profile[profile.name] = len(matched)

        fresh = [p for p in matched if not store.has_seen(p.uid)]
        if dry_run:
            report.sent_by_profile[profile.name] = 0
            continue

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
