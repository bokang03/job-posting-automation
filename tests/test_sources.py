"""각 사이트 파서 테스트. 실제 응답을 저장한 fixture 로만 돌아가므로 네트워크가 필요 없다."""

import json
from pathlib import Path

import pytest

from src.sources import jobkorea, jumpit, rallit, wanted

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- 점핏 -----------------------------------------------------------------


def test_jumpit_parses_every_position_in_page():
    postings = jumpit.parse_page(load_json("jumpit_page.json"))
    assert len(postings) == 3


def test_jumpit_maps_fields_from_real_response():
    postings = jumpit.parse_page(load_json("jumpit_page.json"))
    backend = next(p for p in postings if p.job_id == "54753694")
    assert backend.source == "jumpit"
    assert backend.title == "백엔드 개발자"
    assert backend.company == "티엔에이치"
    assert backend.url == "https://www.jumpit.co.kr/position/54753694"
    assert backend.career_min == 3
    assert backend.career_max == 5
    assert backend.location == "경기 성남시 분당구"
    assert backend.category == "서버/백엔드 개발자"
    assert "Node.js" in backend.tech_stacks
    assert backend.deadline == "2026-09-12"


def test_jumpit_always_open_position_has_no_deadline_date():
    data = {"result": {"positions": [{
        "id": 1, "title": "t", "companyName": "c", "jobCategory": "",
        "techStacks": [], "minCareer": 0, "maxCareer": 0, "locations": [],
        "alwaysOpen": True, "closedAt": None,
    }]}}
    assert jumpit.parse_page(data)[0].deadline == "상시채용"


def test_jumpit_tolerates_missing_optional_fields():
    data = {"result": {"positions": [{"id": 9, "title": "t", "companyName": "c"}]}}
    posting = jumpit.parse_page(data)[0]
    assert posting.job_id == "9"
    assert posting.tech_stacks == ()
    assert posting.location == ""


def test_jumpit_skips_entries_without_id():
    data = {"result": {"positions": [{"title": "제목만 있음"}]}}
    assert jumpit.parse_page(data) == []


# --- 원티드 ---------------------------------------------------------------


def test_wanted_parses_every_item_in_page():
    assert len(wanted.parse_page(load_json("wanted_page.json"))) == 3


def test_wanted_maps_fields_from_real_response():
    postings = wanted.parse_page(load_json("wanted_page.json"))
    security = next(p for p in postings if p.job_id == "219032")
    assert security.source == "wanted"
    assert security.title == "[테크] 보안 운영 담당자"
    assert security.company == "하이퍼리즘"
    assert security.url == "https://www.wanted.co.kr/wd/219032"
    assert security.career_min == 5
    assert security.career_max == 15
    assert security.location == "서울 관악구"


def test_wanted_newbie_posting_starts_at_zero_years():
    postings = wanted.parse_page(load_json("wanted_page.json"))
    intern = next(p for p in postings if p.job_id == "380933")
    assert intern.career_min == 0


@pytest.mark.parametrize(
    "employment_type,expected_tag",
    [("regular", "정규직"), ("intern", "인턴"), ("contract", "계약직"), ("freelance", "프리랜서")],
)
def test_wanted_employment_type_becomes_a_korean_tag(employment_type, expected_tag):
    data = {"data": [{"id": 1, "position": "p", "company": {"name": "c"},
                      "employment_type": employment_type}]}
    assert expected_tag in wanted.parse_page(data)[0].tags


def test_wanted_unknown_employment_type_produces_no_tag():
    data = {"data": [{"id": 1, "position": "p", "company": {"name": "c"},
                      "employment_type": "처음보는값"}]}
    assert wanted.parse_page(data)[0].tags == ()


def test_wanted_intern_tag_can_be_excluded_by_none_keyword():
    data = {"data": [{"id": 1, "position": "서버 개발자", "company": {"name": "c"},
                      "employment_type": "intern"}]}
    assert "인턴" in wanted.parse_page(data)[0].exclusion_haystack()


def test_wanted_missing_annual_fields_mean_career_irrelevant():
    data = {"data": [{"id": 1, "position": "p", "company": {"name": "c"}}]}
    posting = wanted.parse_page(data)[0]
    assert posting.career_min is None
    assert posting.career_max is None


# --- 랠릿 -----------------------------------------------------------------


def test_rallit_parses_every_item_in_page():
    assert len(rallit.parse_page(load_json("rallit_page.json"))) == 3


def test_rallit_maps_fields_from_real_response():
    postings = rallit.parse_page(load_json("rallit_page.json"))
    senior = next(p for p in postings if p.job_id == "4233")
    assert senior.source == "rallit"
    assert senior.title == "[미리캔버스] 시니어 백엔드 개발자"
    assert senior.company == "미리디"
    assert senior.url == "https://www.rallit.com/positions/4233"
    assert "Spring Boot" in senior.tech_stacks


@pytest.mark.parametrize(
    "levels,expected",
    [
        (["BEGINNER"], (0, 0)),
        (["INTERN"], (0, 0)),
        (["JUNIOR"], (1, 3)),
        (["MIDDLE"], (3, 7)),
        (["SENIOR"], (7, None)),
        (["TOP"], (10, None)),
        (["IRRELEVANT"], (None, None)),
        (["SENIOR", "MIDDLE"], (3, None)),
        (["JUNIOR", "MIDDLE"], (1, 7)),
        # IRRELEVANT 가 구체적인 레벨과 섞이면 구체적인 쪽을 따른다
        (["IRRELEVANT", "JUNIOR"], (1, 3)),
        # 신입(BEGINNER)이 함께 붙어 있으면 하한은 0 이 된다
        (["BEGINNER", "MIDDLE"], (0, 7)),
        ([], (None, None)),
        (["처음보는값"], (None, None)),
    ],
)
def test_rallit_job_levels_map_to_year_ranges(levels, expected):
    assert rallit.levels_to_range(levels) == expected


@pytest.mark.parametrize(
    "code,expected",
    [
        ("SEOUL", "서울"),
        ("GANGNAM", "서울 강남"),
        ("GURO_GASAN", "서울 구로/가산"),
        ("MAPO", "서울 마포"),
        ("PANGYO", "경기 판교"),
        ("GYEONGGI", "경기"),
        # 모르는 코드는 빈 문자열로 둬서 지역 필터가 공고를 잘못 걸러내지 않게 한다
        ("ETC", ""),
        ("처음보는코드", ""),
        (None, ""),
    ],
)
def test_rallit_region_codes_map_to_korean(code, expected):
    assert rallit.region_to_korean(code) == expected


def test_rallit_intern_level_is_tagged_so_keyword_filters_can_exclude_it():
    data = {"data": {"items": [{
        "id": 1, "title": "백엔드 개발자", "companyName": "c",
        "jobLevels": ["INTERN"], "url": "https://www.rallit.com/positions/1",
    }]}}
    posting = rallit.parse_page(data)[0]
    assert "인턴" in posting.tags
    assert "인턴" in posting.exclusion_haystack()


# --- 잡코리아 -------------------------------------------------------------


def test_jobkorea_parses_cards_from_real_search_html():
    html = (FIXTURES / "jobkorea_search.html").read_text(encoding="utf-8")
    postings = jobkorea.parse_html(html)
    assert len(postings) >= 4


def test_jobkorea_maps_fields_from_real_search_html():
    html = (FIXTURES / "jobkorea_search.html").read_text(encoding="utf-8")
    postings = jobkorea.parse_html(html)
    kakao = next(p for p in postings if p.job_id == "49763718")
    assert kakao.source == "jobkorea"
    assert kakao.title == "백엔드 개발자"
    assert kakao.company == "카카오뱅크"
    assert kakao.url == "https://www.jobkorea.co.kr/Recruit/GI_Read/49763718"
    assert kakao.location == "경기 성남시"


def test_jobkorea_deduplicates_repeated_cards():
    html = (FIXTURES / "jobkorea_search.html").read_text(encoding="utf-8")
    uids = [p.uid for p in jobkorea.parse_html(html)]
    assert len(uids) == len(set(uids))


@pytest.mark.parametrize(
    "text,expected",
    [
        ("신입", (0, 0)),
        ("경력무관", (None, None)),
        ("신입·경력", (0, None)),
        ("신입/경력", (0, None)),
        ("경력5년↑", (5, None)),
        ("경력 5년↑", (5, None)),
        ("경력3~5년", (3, 5)),
        ("경력", (1, None)),
        ("", (None, None)),
    ],
)
def test_jobkorea_career_text_parses_into_year_range(text, expected):
    assert jobkorea.parse_career_text(text) == expected


@pytest.mark.parametrize(
    "fixture,expected",
    [
        ("jobkorea_detail_trainee.html", "연수생/교육생"),
        ("jobkorea_detail_fulltime.html", "정규직"),
        ("jobkorea_detail_intern.html", "인턴"),
    ],
)
def test_jobkorea_detail_page_yields_employment_type(fixture, expected):
    """고용형태는 검색 목록에 없고 상세 페이지에만 있다."""
    html = (FIXTURES / fixture).read_text(encoding="utf-8")
    assert jobkorea.parse_employment_type(html) == expected


def test_jobkorea_employment_type_drops_the_parenthesised_detail():
    """'인턴 (근무기간 2개월, 정규직 전환 가능)' 에서 괄호 안은 버린다.

    괄호 안에 '정규직' 이 들어 있어서, 그대로 두면 인턴 공고가
    정규직으로 잘못 분류된다.
    """
    html = (FIXTURES / "jobkorea_detail_intern.html").read_text(encoding="utf-8")
    value = jobkorea.parse_employment_type(html)
    assert "정규직" not in value


def test_jobkorea_employment_type_is_empty_when_the_page_has_no_such_field():
    assert jobkorea.parse_employment_type("<html><body><p>점검 중</p></body></html>") == ""


def test_jobkorea_returns_empty_list_for_unrecognisable_html():
    assert jobkorea.parse_html("<html><body><p>서비스 점검 중입니다</p></body></html>") == []
