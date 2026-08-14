"""공고가 프로필 조건에 맞는지 판정한다."""

from __future__ import annotations

import re
from functools import lru_cache

from .config import CareerSpec, KeywordSpec, Profile
from .models import JobPosting

# 공고에 상한 경력이 없을 때 쓸 사실상 무한대 값
_NO_UPPER_BOUND = 99


@lru_cache(maxsize=512)
def _pattern(word: str) -> re.Pattern:
    """키워드를 '영문·숫자 경계' 규칙으로 찾는 정규식.

    앞뒤가 영문자나 숫자면 매칭하지 않는다. 이 규칙 하나로 두 가지가 동시에 해결된다.
      - 'Java' 가 'JavaScript' 에 걸리지 않는다 (뒤에 s 가 붙어 있으므로)
      - 'Spring' 은 'Spring Boot' 에 걸린다 (뒤가 공백이므로)
      - '백엔드' 는 '백엔드개발자' 에 걸린다 (한글은 영문·숫자가 아니므로)
    """
    return re.compile(rf"(?<![a-z0-9]){re.escape(word.lower())}(?![a-z0-9])")


def _contains(haystack: str, word: str) -> bool:
    return _pattern(word).search(haystack) is not None


def _keywords_match(posting: JobPosting, spec: KeywordSpec) -> bool:
    exclusion = posting.exclusion_haystack()
    for word in spec.none:
        if _contains(exclusion, word):
            return False

    haystack = posting.haystack()
    # 그룹끼리는 AND, 그룹 안에서는 OR
    for group in spec.all:
        if not any(_contains(haystack, word) for word in group):
            return False

    if spec.any and not any(_contains(haystack, word) for word in spec.any):
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
