"""제목에 적힌 연차로 경력 정보를 바로잡는다.

랠릿·점핏은 공고마다 경력을 등급(JUNIOR/MIDDLE)으로만 주는데, 회사가 등급을
느슨하게 붙이는 경우가 많다. 실제로 '3-8년차 AI 및 BackEnd 개발 채용' 공고에
JUNIOR 가 붙어 있어 신입 필터를 통과했다. 제목에 숫자로 적혀 있으면 그쪽이 정확하다.
"""

import pytest

from src.career import career_from_title, refine_career
from src.models import JobPosting


@pytest.mark.parametrize(
    "title,expected",
    [
        ("3-8년차 AI 및 BackEnd 개발 채용", (3, 8)),
        ("백엔드 엔지니어(1-3년)", (1, 3)),
        ("백엔드 엔지니어 (1~3년)", (1, 3)),
        ("JAVA 백엔드 (대리급) / 5~8년", (5, 8)),
        ("백엔드 개발자( 5년 이상 )", (5, None)),
        ("시니어 백엔드 개발자 (경력 5년 이상)", (5, None)),
        ("앱 개발자 (React Native, 2년 이상)", (2, None)),
    ],
)
def test_year_range_in_title_is_recognised(title, expected):
    assert career_from_title(title) == expected


@pytest.mark.parametrize(
    "title",
    [
        "백엔드 개발자",
        "백엔드 개발자(신입)",
        "2026년 상반기 개발자 채용",          # 연도는 연차가 아니다
        "[안랩] 2026년 연구소 상시채용",
        "Node.js 백엔드 개발자",
        "웹 개발자 채용 (정규직)",
    ],
)
def test_titles_without_a_year_requirement_give_no_hint(title):
    assert career_from_title(title) is None


def test_implausibly_large_numbers_are_ignored():
    assert career_from_title("개발자 100년 이상") is None


def posting(title, career_min, career_max) -> JobPosting:
    return JobPosting(
        source="rallit", job_id="1", title=title, company="회사",
        url="https://x/1", career_min=career_min, career_max=career_max,
    )


def test_title_years_override_a_wrong_source_range():
    """랠릿이 1~7년이라고 해도 제목이 3-8년차면 제목을 따른다."""
    refined = refine_career(posting("3-8년차 AI 및 BackEnd 개발 채용", 1, 7))
    assert (refined.career_min, refined.career_max) == (3, 8)


def test_posting_without_a_title_hint_is_left_alone():
    original = posting("백엔드 개발자", 0, 3)
    assert refine_career(original) is original


def test_career_irrelevant_posting_stays_irrelevant_without_a_hint():
    original = posting("백엔드 개발자", None, None)
    refined = refine_career(original)
    assert (refined.career_min, refined.career_max) == (None, None)


def test_title_hint_applies_even_when_source_gave_nothing():
    refined = refine_career(posting("백엔드 개발자 (5년 이상)", None, None))
    assert (refined.career_min, refined.career_max) == (5, None)
