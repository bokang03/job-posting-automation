"""제목에 적힌 연차로 경력 정보를 바로잡는다.

랠릿과 점핏은 경력을 등급(JUNIOR / MIDDLE / SENIOR)으로만 준다.
그런데 회사가 등급을 느슨하게 붙이는 일이 잦다. 실제로
'3-8년차 AI 및 BackEnd 개발 채용' 공고에 JUNIOR 가 함께 붙어 있어
신입 필터를 그대로 통과했다.

제목에 숫자로 적혀 있으면 그쪽이 사이트 등급보다 정확하므로 제목을 따른다.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .models import JobPosting

# 사람이 실제로 요구할 수 있는 연차 상한. 이보다 크면 연도나 다른 숫자로 본다.
_MAX_PLAUSIBLE_YEARS = 30

# "3-8년차", "1~3년", "5~8년"
_RANGE = re.compile(r"(?<!\d)(\d{1,2})\s*[-~–]\s*(\d{1,2})\s*년")

# "5년 이상", "2년↑", "경력 3년 이상"
_MINIMUM = re.compile(r"(?<!\d)(\d{1,2})\s*년\s*(?:차)?\s*(?:이상|↑)")


def career_from_title(title: str) -> tuple[int, int | None] | None:
    """제목에서 요구 연차를 읽는다. 없으면 None.

    '2026년 상반기 채용' 처럼 연도가 들어간 제목에 걸리지 않도록
    두 자리 숫자까지만 인정한다.
    """
    text = title or ""

    m = _RANGE.search(text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo <= hi <= _MAX_PLAUSIBLE_YEARS:
            return lo, hi

    m = _MINIMUM.search(text)
    if m:
        lo = int(m.group(1))
        if lo <= _MAX_PLAUSIBLE_YEARS:
            return lo, None

    return None


def refine_career(posting: JobPosting) -> JobPosting:
    """제목에 연차가 적혀 있으면 그 값으로 바꾼 사본을 돌려준다."""
    hint = career_from_title(posting.title)
    if hint is None:
        return posting
    lo, hi = hint
    if (posting.career_min, posting.career_max) == (lo, hi):
        return posting
    return replace(posting, career_min=lo, career_max=hi)
