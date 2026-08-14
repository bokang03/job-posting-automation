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

    영어 단어가 다른 단어 속에 묻혀 잘못 걸리는 것을 막는다.
      - 'Java' 는 'JavaScript' 에 걸리지 않는다 (뒤에 s 가 붙어 있으므로)
      - 'Spring' 은 'Spring Boot' 에 걸린다 (뒤가 공백이므로)
      - 'KB' 는 'KB증권' 에 걸리지만 'KBS미디어' 에는 걸리지 않는다

    경계 검사는 키워드가 영문·숫자로 시작/끝날 때만 건다.
    한글 키워드에까지 걸면 'KB국민은행' 의 '국민은행' 처럼
    앞이 영문자인 경우를 놓친다.
    """
    w = word.lower()
    prefix = r"(?<![a-z0-9])" if w[:1].isascii() and w[:1].isalnum() else ""
    suffix = r"(?![a-z0-9])" if w[-1:].isascii() and w[-1:].isalnum() else ""
    return re.compile(prefix + re.escape(w) + suffix)


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
    company = posting.company.lower()

    for name in profile.exclude_companies:
        if _contains(company, name):
            return False

    # 화이트리스트가 있으면 명단에 있는 회사만 통과시킨다.
    if profile.include_companies and not any(_contains(company, n) for n in profile.include_companies):
        return False

    if not _keywords_match(posting, profile.keywords):
        return False

    if not _career_matches(posting, profile.career):
        return False

    return _location_matches(posting, profile.locations)
