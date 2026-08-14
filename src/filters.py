"""공고가 프로필 조건에 맞는지 판정한다."""

from __future__ import annotations

from .config import CareerSpec, KeywordSpec, Profile
from .models import JobPosting

# 공고에 상한 경력이 없을 때 쓸 사실상 무한대 값
_NO_UPPER_BOUND = 99


def _keywords_match(posting: JobPosting, spec: KeywordSpec) -> bool:
    exclusion = posting.exclusion_haystack()
    for word in spec.none:
        if word.lower() in exclusion:
            return False

    haystack = posting.haystack()
    for word in spec.all:
        if word.lower() not in haystack:
            return False

    if spec.any and not any(word.lower() in haystack for word in spec.any):
        return False

    return True


def _career_matches(posting: JobPosting, spec: CareerSpec) -> bool:
    if posting.career_min is None and posting.career_max is None:
        return spec.include_irrelevant

    lo = posting.career_min if posting.career_min is not None else 0
    hi = posting.career_max if posting.career_max is not None else _NO_UPPER_BOUND

    # 내가 지원 가능한 구간과 공고가 요구하는 구간이 겹치면 통과
    return lo <= spec.max_years and hi >= spec.min_years


def _location_matches(posting: JobPosting, locations: tuple[str, ...]) -> bool:
    if not locations:
        return True
    if not posting.location:
        # 지역 정보를 주지 않는 공고까지 버리면 놓치는 게 많아 통과시킨다.
        return True
    return any(loc in posting.location for loc in locations)


def matches_profile(posting: JobPosting, profile: Profile) -> bool:
    for company in profile.exclude_companies:
        if company.lower() in posting.company.lower():
            return False

    if not _keywords_match(posting, profile.keywords):
        return False

    if not _career_matches(posting, profile.career):
        return False

    return _location_matches(posting, profile.locations)
